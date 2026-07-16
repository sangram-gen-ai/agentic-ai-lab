package com.agentic.lab.springai.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "chat_audit_log")
public class ChatAuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "session_id", nullable = false, length = 64)
    private String sessionId;

    @Column(name = "user_message", nullable = false, columnDefinition = "TEXT")
    private String userMessage;

    @Column(name = "assistant_message", nullable = false, columnDefinition = "TEXT")
    private String assistantMessage;

    @Column(name = "model_id", nullable = false, length = 128)
    private String modelId;

    @Column(name = "client_ip", length = 64)
    private String clientIp;

    @Column(name = "latency_ms")
    private Long latencyMs;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    protected ChatAuditLog() {}

    public ChatAuditLog(
            String sessionId,
            String userMessage,
            String assistantMessage,
            String modelId,
            String clientIp,
            Long latencyMs) {
        this.sessionId = sessionId;
        this.userMessage = userMessage;
        this.assistantMessage = assistantMessage;
        this.modelId = modelId;
        this.clientIp = clientIp;
        this.latencyMs = latencyMs;
        this.createdAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public String getSessionId() {
        return sessionId;
    }

    public String getUserMessage() {
        return userMessage;
    }

    public String getAssistantMessage() {
        return assistantMessage;
    }

    public String getModelId() {
        return modelId;
    }

    public String getClientIp() {
        return clientIp;
    }

    public Long getLatencyMs() {
        return latencyMs;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
