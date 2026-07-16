# Spring AI Service (Phase 2)

Spring Boot 4 (Java 25) + Spring AI service integrated with **AWS Bedrock (Amazon Nova Lite)**.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat` | Chat completion via Bedrock Nova Lite (Redis session + rate limit; Postgres audit) |
| `GET` | `/api/v1/chat/sessions/{sessionId}/audit` | Durable, paginated conversation/audit trail from PostgreSQL — **requires HTTP Basic auth** (`ADMIN_USERNAME`/`ADMIN_PASSWORD`) |
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

PostgreSQL is for durable audit/history; Redis is for fast, ephemeral working state.

## Why PostgreSQL audit?

| Use | Why |
|-----|-----|
| **Conversation / audit log** | Every chat turn is written asynchronously to `chat_audit_log` (session, messages, model, client IP, latency). Survives Redis TTL and container restarts — needed for compliance, debugging, and replaying sessions. The write is fire-and-forget (`@Async`) and swallows its own failures, so a Postgres outage can never fail the chat response itself. |
| **Own schema (`spring_ai`)** | Lives in its own Postgres schema, not `public` — `public` is shared with n8n, whose init script grants `n8n_user` blanket default privileges on every table there. A dedicated schema keeps full chat transcripts out of n8n's reach. See `scripts/init-db.sql`. |
| **Pagination + retention** | `GET .../audit` is paginated (`?page=`/`?size=`, default size 50) so a long-lived/reused `sessionId` can't return an unbounded response. A daily scheduled job (`AUDIT_RETENTION_DAYS`, default 90) purges rows older than the retention window — the durable-storage equivalent of Redis's TTL. |
| **Flyway migration** | Schema is versioned (`V1__chat_audit_log.sql`, targets `spring_ai`); Hibernate `ddl-auto` stays `none`. |
| **Auth on the read endpoint** | `sessionId` is a client-supplied, unauthenticated value — without auth, anyone who knows or guesses one could read another session's full transcript. `GET .../audit` requires HTTP Basic auth for this reason. |

```bash
# After a chat, inspect durable history (requires Basic auth)
curl -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" \
  "http://localhost:8080/api/v1/chat/sessions/<sessionId>/audit?page=0&size=20"

# Or via psql — note the "spring_ai" schema, not "public"
docker compose exec postgres psql -U agentic_admin -d agentic_ai \
  -c "SELECT id, session_id, left(user_message,40), latency_ms, created_at FROM spring_ai.chat_audit_log ORDER BY id DESC LIMIT 5;"
```

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
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | HTTP Basic auth for `GET /api/v1/chat/sessions/**` |
| `AUDIT_RETENTION_DAYS` | Days before a chat audit log entry is purged. Default: `90` |

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
- `ChatAuditServiceTest` covers the audit write's failure isolation (a repository exception must never propagate) and the retention-purge cutoff logic.
- `ChatAuditLogRepositoryTest` is a `@DataJpaTest` against a real Postgres via Testcontainers — runs the actual Flyway migration against the `spring_ai` schema and verifies save/pagination/purge against real SQL, not a mock.
- `ChatControllerTest` is a `@WebMvcTest` with mocked `ChatClient`/services covering the happy path, validation (400), rate-limit (429), and the audit endpoint's auth (401/403/200) and pagination.
- `BedrockChatIntegrationTest` is a live AWS Bedrock (Nova Lite) `@SpringBootTest` — Postgres + Redis via Testcontainers, real HTTP calls to `/api/v1/chat`. **Skipped automatically** when `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are unset (so CI without AWS stays green). Tagged `bedrock`.

```bash
# Run the live Bedrock integration test (needs AWS creds + Docker for Testcontainers)
set -a && source ../../.env && set +a
mvn test -Dtest=BedrockChatIntegrationTest
# or: mvn test -Dgroups=bedrock
```

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

# Durable audit trail (PostgreSQL, requires Basic auth)
curl -u admin:change_me_admin "http://localhost:8080/api/v1/chat/sessions/<sessionId>/audit"
```


## Internal URL (for n8n / FastAPI)

```
http://spring-ai:8080
```
