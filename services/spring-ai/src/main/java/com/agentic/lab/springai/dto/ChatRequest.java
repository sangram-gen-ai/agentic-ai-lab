package com.agentic.lab.springai.dto;

import jakarta.validation.constraints.NotBlank;

public record ChatRequest(
        @NotBlank(message = "message is required") String message,
        /** Optional. Reuse to continue a multi-turn conversation stored in Redis. */
        String sessionId
) {}
