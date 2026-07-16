package com.agentic.lab.springai.dto;

public record ChatResponse(
        String message,
        String model,
        String sessionId,
        int rateLimitRemaining
) {}
