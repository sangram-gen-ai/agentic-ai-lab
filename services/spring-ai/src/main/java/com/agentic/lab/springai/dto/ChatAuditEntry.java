package com.agentic.lab.springai.dto;

import java.time.Instant;

public record ChatAuditEntry(
        Long id,
        String sessionId,
        String userMessage,
        String assistantMessage,
        String modelId,
        String clientIp,
        Long latencyMs,
        Instant createdAt
) {}
