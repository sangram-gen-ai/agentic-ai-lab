# Agentic AI Enterprise Lab

Local development platform for agentic AI workflows — orchestration, persistence, vector search, object storage, and document processing.

---

## Quick Start

```bash
cd agentic-ai-lab
cp .env.example .env          # edit passwords before production use
docker compose up -d
docker compose ps
```

Stop: `docker compose down`  
Logs: `docker compose logs -f <service>`

---

## Login Credentials

All passwords are defined in `.env`. Default values below match a fresh `cp .env.example .env`.

> **Security:** These are development defaults. Change every `change_me_*` value in `.env` before sharing or deploying.

### Services with a web login

| Service | URL | Username / Email | Password (`.env` key) |
|---------|-----|------------------|------------------------|
| **n8n** | http://localhost:5678 | *Set on first visit* | *You choose at setup* |
| **pgAdmin** | http://localhost:5050 | `admin@example.com` | `change_me_pgadmin` → `PGADMIN_PASSWORD` |
| **MinIO Console** | http://localhost:9001 | `agentic_minio` | `change_me_minio` → `MINIO_ROOT_PASSWORD` |

### Database & cache credentials

| Service | Host (Mac) | Host (containers) | Username | Password (`.env` key) | Database |
|---------|------------|-------------------|----------|------------------------|----------|
| **PostgreSQL** | `localhost:5432` | `postgres:5432` | `agentic_admin` | `change_me_postgres` → `POSTGRES_PASSWORD` | `agentic_ai` |
| **n8n DB user** | — | `postgres:5432` | `n8n_user` | `change_me_n8n` → `N8N_DB_PASSWORD` | `agentic_ai` |
| **Redis** | `localhost:6379` | `redis:6379` | — | `change_me_redis` → `REDIS_PASSWORD` | — |

### Services with no login (local dev)

| Service | URL | Notes |
|---------|-----|-------|
| **Qdrant Dashboard** | http://localhost:6333/dashboard | No auth enabled in Phase 1 |
| **Qdrant API** | http://localhost:6333 | Health: http://localhost:6333/readyz |
| **MinIO API** | http://localhost:9000 | Use `agentic_minio` / `MINIO_ROOT_PASSWORD` for S3 clients |

---

## All Services

### 1. n8n — Workflow Engine

| | |
|---|---|
| **Purpose** | Visual workflow automation, webhooks, multi-agent orchestration (Phase 5) |
| **Container** | `agentic-n8n` |
| **Browser URL** | http://localhost:5678 |
| **Internal URL** | `http://n8n:5678` |
| **Data** | Workflows stored in PostgreSQL (`agentic_ai`), not SQLite |
| **Local files** | `data/n8n/` (encryption keys only) |
| **Exports** | `workflows/n8n/` |

**First-time setup**

1. Open http://localhost:5678
2. Create your owner account (email + password — not in `.env`)
3. Workflows persist across restarts via PostgreSQL

**PostgreSQL tables created by n8n**

- `workflow_entity` — workflow definitions
- `credentials_entity` — stored API keys / secrets
- `execution_entity` — run history
- `execution_data` — execution payloads

---

### 2. PostgreSQL — Primary Database

| | |
|---|---|
| **Purpose** | n8n persistence, Spring Boot data (Phase 2), audit logs |
| **Container** | `agentic-postgres` |
| **Browser / GUI** | Use pgAdmin (below) |
| **Direct connect (Mac)** | `postgresql://agentic_admin:change_me_postgres@localhost:5432/agentic_ai` |
| **Internal connect** | `postgresql://agentic_admin:change_me_postgres@postgres:5432/agentic_ai` |
| **Data** | `data/postgres/pgdata/` |

**Users**

| User | Password | Access |
|------|----------|--------|
| `agentic_admin` | `POSTGRES_PASSWORD` | Full admin on `agentic_ai` |
| `n8n_user` | `N8N_DB_PASSWORD` | n8n tables in `agentic_ai` |

---

### 3. pgAdmin — Database UI

| | |
|---|---|
| **Purpose** | Browse tables, run SQL, inspect n8n workflow data |
| **Container** | `agentic-pgadmin` |
| **URL** | http://localhost:5050 |
| **Login email** | `admin@example.com` |
| **Login password** | `PGADMIN_PASSWORD` (default: `change_me_pgadmin`) |

**Pre-registered server**

- Name: **Agentic PostgreSQL**
- Host: `postgres` (internal — works inside Docker network)
- When prompted for DB password, enter `POSTGRES_PASSWORD` (`change_me_postgres`)

---

### 4. Redis — Cache & Sessions

| | |
|---|---|
| **Purpose** | Session cache, rate limiting (Phase 2 Spring Boot) |
| **Container** | `agentic-redis` |
| **Host (Mac)** | `localhost:6379` |
| **Internal** | `redis:6379` |
| **Password** | `REDIS_PASSWORD` (default: `change_me_redis`) |
| **Data** | `data/redis/` |

**Test connection**

```bash
docker compose exec redis redis-cli -a change_me_redis ping
# Expected: PONG
```

---

### 5. Qdrant — Vector Database

| | |
|---|---|
| **Purpose** | Embedding storage and similarity search (Phase 4 RAG) |
| **Container** | `agentic-qdrant` |
| **Dashboard** | http://localhost:6333/dashboard |
| **API** | http://localhost:6333 |
| **Internal API** | `http://qdrant:6333` |
| **gRPC** | `localhost:6334` / `qdrant:6334` |
| **Auth** | None (local dev) |
| **Data** | `data/qdrant/` |

---

### 6. MinIO — S3 Object Storage

| | |
|---|---|
| **Purpose** | Document uploads, PDFs, images (Phase 3 FastAPI) |
| **Container** | `agentic-minio` |
| **Console URL** | http://localhost:9001 |
| **API URL** | http://localhost:9000 |
| **Internal API** | `http://minio:9000` |
| **Username** | `agentic_minio` → `MINIO_ROOT_USER` |
| **Password** | `change_me_minio` → `MINIO_ROOT_PASSWORD` |
| **Default bucket** | `documents` (created by `minio-init`) |
| **Data** | `data/minio/` |

**S3-compatible endpoint (from containers)**

```
Endpoint: http://minio:9000
Access Key: agentic_minio
Secret Key: change_me_minio
Bucket: documents
```

---

### 7. Spring AI — API Service (Phase 2, not yet running)

| | |
|---|---|
| **Purpose** | Spring Boot + Spring AI + AWS Bedrock (Nova Lite) |
| **Folder** | `services/spring-ai/` |
| **Planned URL** | http://localhost:8080 |
| **Internal URL** | `http://spring-ai:8080` |
| **Connects to** | `postgres:5432`, `redis:6379`, AWS Bedrock (external) |

Uncomment `spring-ai` in `docker-compose.yml` when ready.

---

### 8. Fast API — Document Ingestion (Phase 3, not yet running)

| | |
|---|---|
| **Purpose** | Upload, OCR, extract text, AI utilities |
| **Folder** | `services/fast-api/` |
| **Planned URL** | http://localhost:8000 |
| **Internal URL** | `http://fast-api:8000` |
| **Connects to** | `minio:9000`, `qdrant:6333`, `postgres:5432` |
| **Documents** | `documents/{resumes,invoices,contracts,healthcare,claims}/` |

Uncomment `fast-api` in `docker-compose.yml` when ready.

---

## Credential Quick Reference

Copy-paste defaults from `.env`:

```
# pgAdmin
Email:    admin@example.com
Password: change_me_pgadmin

# MinIO Console
User:     agentic_minio
Password: change_me_minio

# PostgreSQL (psql / DBeaver / Spring)
User:     agentic_admin
Password: change_me_postgres
Database: agentic_ai
Host:     localhost  (Mac)  |  postgres  (containers)
Port:     5432

# Redis
Password: change_me_redis

# n8n database user (internal — used by n8n container)
User:     n8n_user
Password: change_me_n8n
Database: agentic_ai
```

---

## Networking

### You on your Mac → use `localhost`

```bash
open http://localhost:5678      # n8n
open http://localhost:5050      # pgAdmin
open http://localhost:9001      # MinIO
open http://localhost:6333/dashboard  # Qdrant
```

### Containers → use service names on `agentic-ai-network`

| Service | Internal address |
|---------|------------------|
| PostgreSQL | `postgres:5432` |
| Redis | `redis:6379` |
| Qdrant | `http://qdrant:6333` |
| MinIO | `http://minio:9000` |
| n8n | `http://n8n:5678` |
| Spring AI | `http://spring-ai:8080` |
| Fast API | `http://fast-api:8000` |

Never use `localhost` between containers.

---

## Project Structure

```
agentic-ai-lab/
├── docker-compose.yml
├── .env
├── README.md
├── data/                  # persistent storage (bind mounts)
├── services/
│   ├── spring-ai/         # Phase 2
│   └── fast-api/          # Phase 3
├── documents/             # sample files by category
├── scripts/
│   ├── init-db.sql
│   ├── backup.sh
│   └── restore.sh
├── workflows/n8n/         # exported workflow JSON
└── prompts/agents/        # agent system prompts
```

---

## Backup & Restore

```bash
./scripts/backup.sh
./scripts/restore.sh backups/<timestamp>
```

---

## Reset All Data

```bash
docker compose down
rm -rf data/postgres/pgdata data/n8n/* data/redis/* data/qdrant/* data/minio/*
docker compose up -d
```

---

## Phase Roadmap

| Phase | Component | Status |
|-------|-----------|--------|
| 1 | Docker infrastructure | **Running** |
| 2 | `services/spring-ai/` | Planned |
| 3 | `services/fast-api/` | Planned |
| 4 | RAG + `prompts/agents/` | Planned |
| 5 | `workflows/n8n/` multi-agent | Planned |

---

## Troubleshooting

**Forgot a password**  
Check `.env` in the project root — all credentials are defined there.

**n8n won't connect to PostgreSQL**  
Ensure `N8N_DB_NAME=agentic_ai` and `N8N_DB_PASSWORD` matches `scripts/init-db.sql`.

**pgAdmin won't start**  
Email must be a valid format (e.g. `admin@example.com`, not `.local` domains).

**Port in use**  
Change ports in `.env` (e.g. `N8N_PORT=5679`).

**PostgreSQL won't init**  
Ensure `data/postgres/` uses the `pgdata` subdirectory (`PGDATA` is set in compose).
