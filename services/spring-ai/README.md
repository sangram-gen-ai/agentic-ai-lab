# Spring AI Service (Phase 2)

Spring Boot 4 (Java 25) + Spring AI service integrated with **AWS Bedrock (Amazon Nova Lite)**.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat` | Chat completion via Bedrock Nova Lite (session + rate limit via Redis) |
| `GET` | `/actuator/health` | Health check |
| `GET` | `/swagger-ui/index.html` | Interactive OpenAPI (Swagger) UI |
| `GET` | `/v3/api-docs` | Raw OpenAPI spec |

### Chat request / response

```json
// Request — omit sessionId on first turn; reuse it for follow-ups
{ "message": "What is agentic AI?", "sessionId": null }

// Response
{
  "message": "...",
  "model": "amazon.nova-lite-v1:0",
  "sessionId": "uuid-from-redis-session",
  "rateLimitRemaining": 19
}
```

Rate limit exceeded → HTTP `429` with `Retry-After`.

## Why Redis?

| Use | Why |
|-----|-----|
| **Chat session cache** | Multi-turn context lives in Redis (TTL 30m), not in the client or JVM memory. n8n / FastAPI can continue a conversation by sending the same `sessionId`. Survives container restarts better than in-memory maps; shared if you scale replicas later. |
| **Rate limiting** | Bedrock calls cost money. Redis `INCR` + `EXPIRE` caps requests per **client IP** (default 20/min), independent of `sessionId` — a caller that never sends a session (e.g. a runaway/stateless loop, the exact case this protects against) would otherwise get a fresh rate-limit key on every call and never be throttled. The TTL self-heals on the next request if a prior `EXPIRE` is ever lost, instead of leaving that client locked out forever. |

PostgreSQL is for durable audit/history (Phase 2 remaining); Redis is for fast, ephemeral working state.

## Configuration

Uses environment variables from the root `.env`:

| Variable | Purpose |
|----------|---------|
| `SPRING_DATASOURCE_URL` | PostgreSQL (`postgres:5432/agentic_ai`) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | DB credentials |
| `REDIS_HOST` / `REDIS_PASSWORD` | Redis session cache + rate limits |
| `AWS_REGION` | Bedrock region |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS credentials |
| `BEDROCK_MODEL_ID` | Default: `amazon.nova-lite-v1:0` |

## Local development (without Docker)

```bash
cd services/spring-ai
# Set AWS credentials in environment or ~/.aws/credentials
mvn spring-boot:run \
  -Dspring-boot.run.arguments="--SPRING_DATASOURCE_URL=jdbc:postgresql://localhost:5432/agentic_ai"
```

## Docker (recommended)

From project root:

```bash
# Add AWS credentials to .env first
docker compose up -d --build spring-ai
docker compose logs -f spring-ai
```

## Automated tests

```bash
cd services/spring-ai
mvn test
```

- `RateLimitServiceTest` / `ChatSessionServiceTest` spin up a real Redis via Testcontainers (requires Docker) and cover the fixed-window limiter, TTL self-heal, history ordering/trimming, and concurrent-append safety.
- `ChatControllerTest` is a `@WebMvcTest` with mocked `ChatClient`/services covering the happy path, validation (400), and rate-limit (429) responses.

## Manual smoke test

```bash
# Health
curl http://localhost:8080/actuator/health

# Chat (requires valid AWS Bedrock credentials)
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is agentic AI in one sentence?"}'

# Follow-up (reuse sessionId from previous response)
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Give an enterprise example.", "sessionId": "<sessionId>"}'
```


## Internal URL (for n8n / FastAPI)

```
http://spring-ai:8080
```
