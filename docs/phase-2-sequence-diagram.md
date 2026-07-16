# Phase 2 — Spring Boot + Spring AI + Bedrock: Sequence Diagram

> Companion to [`phase-checklist.md`](./phase-checklist.md) and
> [`services/spring-ai/README.md`](../services/spring-ai/README.md). Reflects the
> actual `depends_on` wiring in `docker-compose.yml` and the request path in
> `ChatController` / Redis / Flyway / Bedrock Converse.

Phase 2 adds the **`spring-ai`** service on top of Phase 1 infra. It waits for
**PostgreSQL** and **Redis** to be healthy, runs Flyway into schema `spring_ai`
(separate from n8n's `public`), then serves chat via Spring AI → AWS Bedrock
(Amazon Nova Lite). Redis holds ephemeral session history + IP rate limits;
Postgres holds durable audit rows (async, fire-and-forget).

## Visual (PNG)

![Phase 2 Spring AI chat sequence](./phase-2-sequence-diagram.png)

*Source Mermaid: [`phase-2-sequence-diagram.mmd`](./phase-2-sequence-diagram.mmd) · Rendered at 1568×1496*

## Mermaid source

```mermaid
sequenceDiagram
    actor Dev as Developer / Client
    participant Compose as Docker Compose
    participant PG as PostgreSQL
    participant Redis
    participant Spring as spring-ai
    participant Bedrock as AWS Bedrock
    participant Nova as Amazon Nova Lite

    Note over Dev,Nova: Startup (gated on Phase 1 healthchecks)
    Dev->>Compose: docker compose up -d --build spring-ai

    Compose->>PG: wait until service_healthy
    Compose->>Redis: wait until service_healthy
    Compose->>Spring: start (env_file .env, port 8080)

    Spring->>PG: Flyway migrate schema spring_ai (V1__chat_audit_log)
    PG-->>Spring: chat_audit_log ready
    Spring->>Redis: connect (REDIS_HOST / REDIS_PASSWORD)
    Redis-->>Spring: ready
    Spring-->>Compose: actuator/health UP (container healthy)

    Note over Dev,Nova: POST /api/v1/chat (open — no Basic auth)
    Dev->>Spring: POST /api/v1/chat {message, sessionId?}

    Spring->>Spring: resolveSessionId (UUID if omitted)
    Spring->>Redis: INCR rate:chat:{clientIp} + EXPIRE
    alt over limit (default 20/min)
        Redis-->>Spring: count > max
        Spring-->>Dev: 429 rate_limit_exceeded + Retry-After
    else under limit
        Redis-->>Spring: remaining
        Spring->>Redis: GET chat:session:{sessionId}
        Redis-->>Spring: prior turns (or empty)
        Spring->>Bedrock: ChatClient Converse (Nova Lite + history + user msg)
        Bedrock->>Nova: invoke model
        Nova-->>Bedrock: completion
        Bedrock-->>Spring: assistant message
        Spring->>Redis: SET chat:session:{sessionId} (TTL 30m, cap 20 msgs)
        Spring-)PG: @Async INSERT spring_ai.chat_audit_log
        Spring-->>Dev: 200 {message, model, sessionId, rateLimitRemaining}
    end

    Note over Dev,Nova: Follow-up turn (same sessionId → Redis history)
    Dev->>Spring: POST /api/v1/chat {message, sessionId}
    Spring->>Redis: rate limit + load history
    Spring->>Bedrock: Converse with prior turns
    Bedrock-->>Spring: contextual reply
    Spring->>Redis: append turn
    Spring-)PG: @Async audit row
    Spring-->>Dev: 200 ChatResponse

    Note over Dev,Nova: GET audit trail (HTTP Basic — ADMIN_USERNAME / PASSWORD)
    Dev->>Spring: GET /api/v1/chat/sessions/{sessionId}/audit (Basic auth)
    Spring->>PG: SELECT spring_ai.chat_audit_log (paginated)
    PG-->>Spring: rows
    Spring-->>Dev: 200 [{userMessage, assistantMessage, latencyMs, ...}]
```

## Notes

- **`spring-ai` depends_on** `postgres: service_healthy` and `redis: service_healthy` only — Qdrant/MinIO/n8n are unused in Phase 2.
- **Redis vs Postgres:** Redis = hot session context + rate counters (TTL). Postgres `spring_ai.chat_audit_log` = durable history (survives Redis TTL; async write must not fail the chat response).
- **Rate limit key is client IP**, not `sessionId` — a caller that omits `sessionId` would otherwise mint a new key every request and bypass the limiter.
- **Audit read is authenticated** because `sessionId` is client-supplied; without Basic auth, anyone who guessed an ID could read another session's transcript.
- **Bedrock** is external (AWS). Credentials come from `.env` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `BEDROCK_MODEL_ID=amazon.nova-lite-v1:0`).
- Live coverage: `BedrockChatIntegrationTest` (skipped when AWS keys are unset).
