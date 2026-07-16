# Phase 1 — Docker Compose Infrastructure: Sequence Diagram

> Companion to [`phase-checklist.md`](./phase-checklist.md). Reflects the actual
> `depends_on`/healthcheck wiring in the root `docker-compose.yml`, not just the
> checklist prose.

Startup order is governed entirely by `depends_on: condition: service_healthy`.
Four services have no dependencies and start in parallel; two dependents
(`pgadmin`, `n8n`) gate on Postgres becoming healthy, and `minio-init` gates on
MinIO becoming healthy. Redis and Qdrant have **no dependents within Phase 1**
— they're provisioned here for Phase 2 (Spring Boot cache/rate-limit) and
Phase 4 (RAG vector search) respectively.

## Visual (PNG)

![Phase 1 Docker Compose startup sequence](./phase-1-sequence-diagram.png)

*Source Mermaid: [`phase-1-sequence-diagram.mmd`](./phase-1-sequence-diagram.mmd) · Rendered at 1568×1182*

## Mermaid source

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant Compose as Docker Compose
    participant PG as PostgreSQL
    participant Redis
    participant Qdrant
    participant MinIO
    participant MinIOInit as minio-init
    participant PgAdmin as pgAdmin
    participant N8N as n8n

    Dev->>Compose: docker compose up -d

    par No dependencies — start in parallel
        Compose->>PG: start (init-db.sql, POSTGRES_* env)
        Compose->>Redis: start (--appendonly yes --requirepass)
        Compose->>Qdrant: start (persistent volume)
        Compose->>MinIO: start (console :9001)
    end

    loop pg_isready, every 10s, up to 5 retries
        PG-->>Compose: healthcheck
    end
    Note over PG: healthy

    loop redis-cli -a *** ping, every 10s, up to 5 retries
        Redis-->>Compose: healthcheck
    end
    Note over Redis: healthy (no Phase-1 dependent — reserved for Phase 2)

    loop GET /readyz, every 15s, start_period 15s
        Qdrant-->>Compose: healthcheck
    end
    Note over Qdrant: healthy (no Phase-1 dependent — reserved for Phase 4)

    loop TCP check :9000, every 15s, start_period 15s
        MinIO-->>Compose: healthcheck
    end
    Note over MinIO: healthy

    par Gated on the healthchecks above
        Compose->>PgAdmin: start (depends_on postgres: service_healthy)
        Compose->>N8N: start (depends_on postgres: service_healthy)
        Compose->>MinIOInit: start (depends_on minio: service_healthy)
    end

    MinIOInit->>MinIO: mc alias set local
    MinIOInit->>MinIO: mc mb local/documents --ignore-existing
    MinIOInit-->>Compose: bucket ready, container exits (one-shot)

    PgAdmin->>PG: connect via scripts/pgadmin-servers.json
    N8N->>PG: connect (DB_POSTGRESDB_*), create workflow_entity, credentials_entity, execution_entity in schema "public"

    Note over Dev,N8N: Smoke test (checklist item)
    Dev->>PgAdmin: login (PGADMIN_DEFAULT_EMAIL / PASSWORD)
    Dev->>MinIO: open console :9001
    Dev->>Qdrant: open dashboard :6333/dashboard
    Dev->>N8N: open UI :5678
```

## Notes

- **`postgres`** is the only service with two direct dependents (`pgadmin`, `n8n`) — it's the critical path for Phase 1 startup time.
- **`minio-init`** is a one-shot init container (`image: minio/mc`), not a long-running service — it runs `mc alias`/`mc mb` once and exits, which is why it isn't part of the steady-state topology.
- **Redis and Qdrant are provisioned, not yet consumed**, in Phase 1 — the compose file's own comments mark them `Phase 2 Spring Boot` and `Phase 4 RAG` respectively. This diagram shows them starting and passing health checks, but nothing in Phase 1 itself talks to them.
- n8n's `DB_POSTGRESDB_SCHEMA` is `public` — the same schema later split from `spring_ai` in Phase 2 (see `scripts/init-db.sql` and `services/spring-ai/README.md`) to isolate audit data from n8n's blanket schema privileges.
