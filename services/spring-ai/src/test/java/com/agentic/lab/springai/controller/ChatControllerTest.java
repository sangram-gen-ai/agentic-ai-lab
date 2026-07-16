package com.agentic.lab.springai.controller;

import com.agentic.lab.springai.dto.ChatRequest;
import com.agentic.lab.springai.service.ChatSessionService;
import com.agentic.lab.springai.service.RateLimitExceededException;
import com.agentic.lab.springai.service.RateLimitService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Collections;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.RETURNS_DEEP_STUBS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ChatController.class)
@Import({ApiExceptionHandler.class, ChatControllerTest.MockChatClientConfig.class})
@TestPropertySource(properties = "spring.ai.bedrock.converse.chat.options.model=amazon.nova-lite-v1:0")
class ChatControllerTest {

    @TestConfiguration
    static class MockChatClientConfig {
        @Bean
        ChatClient chatClient() {
            return mock(ChatClient.class, RETURNS_DEEP_STUBS);
        }
    }

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ChatClient chatClient;

    @MockitoBean
    ChatSessionService chatSessionService;

    @MockitoBean
    RateLimitService rateLimitService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        reset(chatClient);
        when(chatSessionService.resolveSessionId(any()))
                .thenAnswer(inv -> {
                    String sessionId = inv.getArgument(0);
                    return sessionId == null ? "generated-session-id" : sessionId;
                });
        when(chatSessionService.getHistory(any())).thenReturn(Collections.emptyList());
        when(rateLimitService.checkAndIncrement(any())).thenReturn(19);
        when(chatClient.prompt().messages(anyList()).call().content()).thenReturn("mocked answer");
    }

    @Test
    void chatReturnsAnswerAndSessionMetadata() throws Exception {
        ChatRequest request = new ChatRequest("hello", null);

        mockMvc.perform(post("/api/v1/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("mocked answer"))
                .andExpect(jsonPath("$.model").value("amazon.nova-lite-v1:0"))
                .andExpect(jsonPath("$.sessionId").value("generated-session-id"))
                .andExpect(jsonPath("$.rateLimitRemaining").value(19));

        verify(chatSessionService).append("generated-session-id", "hello", "mocked answer");
    }

    @Test
    void blankMessageIsRejected() throws Exception {
        ChatRequest request = new ChatRequest("   ", null);

        mockMvc.perform(post("/api/v1/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rateLimitExceededReturns429WithRetryAfter() throws Exception {
        when(rateLimitService.checkAndIncrement(any()))
                .thenThrow(new RateLimitExceededException(20, 60));

        ChatRequest request = new ChatRequest("hello", null);

        mockMvc.perform(post("/api/v1/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().string("Retry-After", "60"))
                .andExpect(jsonPath("$.error").value("rate_limit_exceeded"));
    }
}
