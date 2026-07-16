package com.agentic.lab.springai.controller;

import com.agentic.lab.springai.dto.ChatAuditEntry;
import com.agentic.lab.springai.dto.ChatRequest;
import com.agentic.lab.springai.dto.ChatResponse;
import com.agentic.lab.springai.entity.ChatAuditLog;
import com.agentic.lab.springai.service.ChatAuditService;
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
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
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
    private final ChatAuditService chatAuditService;
    private final String modelId;

    public ChatController(
            ChatClient chatClient,
            ChatSessionService chatSessionService,
            RateLimitService rateLimitService,
            ChatAuditService chatAuditService,
            @Value("${spring.ai.bedrock.converse.chat.options.model}") String modelId) {
        this.chatClient = chatClient;
        this.chatSessionService = chatSessionService;
        this.rateLimitService = rateLimitService;
        this.chatAuditService = chatAuditService;
        this.modelId = modelId;
    }

    @PostMapping("/chat")
    public ChatResponse chat(@Valid @RequestBody ChatRequest request, HttpServletRequest httpRequest) {
        String sessionId = chatSessionService.resolveSessionId(request.sessionId());
        String clientIp = clientKey(httpRequest);
        int remaining = rateLimitService.checkAndIncrement(clientIp);

        List<Message> messages = toMessages(chatSessionService.getHistory(sessionId));
        messages.add(new UserMessage(request.message()));

        long started = System.currentTimeMillis();
        String answer = chatClient.prompt()
                .messages(messages)
                .call()
                .content();
        long latencyMs = System.currentTimeMillis() - started;

        chatSessionService.append(sessionId, request.message(), answer);
        chatAuditService.record(sessionId, request.message(), answer, modelId, clientIp, latencyMs);

        return new ChatResponse(answer, modelId, sessionId, remaining);
    }

    /**
     * Durable conversation history from PostgreSQL (survives Redis TTL).
     * Paginated: a session reused indefinitely has no bound otherwise.
     */
    @GetMapping("/chat/sessions/{sessionId}/audit")
    public List<ChatAuditEntry> auditTrail(
            @PathVariable String sessionId,
            @PageableDefault(size = 50, sort = "createdAt", direction = Sort.Direction.ASC) Pageable pageable) {
        return chatAuditService.findBySession(sessionId, pageable).stream()
                .map(ChatController::toEntry)
                .toList();
    }

    private static ChatAuditEntry toEntry(ChatAuditLog log) {
        return new ChatAuditEntry(
                log.getId(),
                log.getSessionId(),
                log.getUserMessage(),
                log.getAssistantMessage(),
                log.getModelId(),
                log.getClientIp(),
                log.getLatencyMs(),
                log.getCreatedAt());
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
