package com.agentic.lab.springai.controller;

import com.agentic.lab.springai.dto.ChatRequest;
import com.agentic.lab.springai.dto.ChatResponse;
import com.agentic.lab.springai.service.ChatSessionService;
import com.agentic.lab.springai.service.ChatSessionService.ChatTurn;
import com.agentic.lab.springai.service.RateLimitService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import java.util.ArrayList;
import java.util.List;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class ChatController {

    private final ChatClient chatClient;
    private final ChatSessionService chatSessionService;
    private final RateLimitService rateLimitService;
    private final String modelId;

    public ChatController(
            ChatClient chatClient,
            ChatSessionService chatSessionService,
            RateLimitService rateLimitService,
            @Value("${spring.ai.bedrock.converse.chat.options.model}") String modelId) {
        this.chatClient = chatClient;
        this.chatSessionService = chatSessionService;
        this.rateLimitService = rateLimitService;
        this.modelId = modelId;
    }

    @PostMapping("/chat")
    public ChatResponse chat(@Valid @RequestBody ChatRequest request, HttpServletRequest httpRequest) {
        String sessionId = chatSessionService.resolveSessionId(request.sessionId());
        int remaining = rateLimitService.checkAndIncrement(clientKey(httpRequest));

        List<Message> messages = toMessages(chatSessionService.getHistory(sessionId));
        messages.add(new UserMessage(request.message()));

        String answer = chatClient.prompt()
                .messages(messages)
                .call()
                .content();

        chatSessionService.append(sessionId, request.message(), answer);
        return new ChatResponse(answer, modelId, sessionId, remaining);
    }

    private static String clientKey(HttpServletRequest httpRequest) {
        String forwardedFor = httpRequest.getHeader("X-Forwarded-For");
        if (forwardedFor != null && !forwardedFor.isBlank()) {
            return forwardedFor.split(",")[0].trim();
        }
        return httpRequest.getRemoteAddr();
    }

    private static List<Message> toMessages(List<ChatTurn> history) {
        List<Message> messages = new ArrayList<>(history.size());
        for (ChatTurn turn : history) {
            if ("assistant".equalsIgnoreCase(turn.role())) {
                messages.add(new AssistantMessage(turn.content()));
            } else {
                messages.add(new UserMessage(turn.content()));
            }
        }
        return messages;
    }
}
