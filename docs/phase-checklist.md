# Agentic AI Enterprise Lab — Phase Checklist

> Exported from the interactive canvas. Progress as of **Jul 16, 2026**.
>
> Canvas (interactive): open beside chat in Cursor — `agentic-ai-lab-phase-checklist.canvas.tsx`

**Overall:** Phase 1 complete · Phase 2 complete (10/10) · Phase 3 complete (10/10) · Phases 4–5 pending

| Metric | Value |
|--------|-------|
| Current focus | Phase 4 |
| Tasks complete | 31 / 51 |
| Overall progress | ~61% |

---

## Phase 1 — Docker Compose Infrastructure

*n8n, PostgreSQL, pgAdmin, Qdrant, Redis, MinIO* · **11/11 Done**

- [x] Initialize repo with docker-compose.yml, .env.example, and README
- [x] Define shared Docker network and bind mounts under data/ for all services
- [x] Add PostgreSQL with init scripts, credentials, and health check
- [x] Add pgAdmin and connect it to PostgreSQL
- [x] Add Redis with persistence and health check
- [x] Add Qdrant with persistent volume and REST API port exposed
- [x] Add MinIO with console access and default bucket creation
- [x] Add n8n linked to PostgreSQL for workflow persistence
- [x] Wire all service URLs and secrets through .env (no hardcoded credentials)
- [x] Verify every service starts with docker compose up and passes health checks
- [x] Smoke test: pgAdmin login, MinIO console, Qdrant dashboard, n8n UI

**Exit criteria:** All 6 services running locally, reachable, and persistent across restarts.

---

## Phase 2 — Spring Boot + Spring AI + Bedrock

*Enterprise API layer with Amazon Nova Lite via AWS Bedrock* · **10/10 Done**

- [x] Bootstrap Spring Boot 4 project (Java 25) with actuator and OpenAPI
- [x] Add Spring AI and Bedrock Converse model dependencies
- [x] Configure AWS credentials and Bedrock client (Nova Lite model ID)
- [x] Implement POST /api/v1/chat using Spring AI ChatClient
- [x] Add system prompt template and request/response DTOs with validation
- [x] Integrate Redis for chat session cache and rate limiting
- [x] Integrate PostgreSQL for conversation or audit logging (JPA/Flyway)
- [x] Add Dockerfile and register spring-ai service in docker-compose
- [x] Write integration test for Bedrock call (or local mock profile)
- [x] Verify end-to-end: chat via API/Swagger through Spring to Nova Lite

**Exit criteria:** Working chat API backed by Nova Lite, with data persisted in Phase 1 infra.

---

## Phase 3 — FastAPI Document Ingestion

*Document upload, OCR utilities, and AI helper endpoints* · **10/10 Done**

- [x] Bootstrap FastAPI project with uvicorn, pydantic settings, and /health
- [x] Implement POST /documents/upload with file type validation (PDF, PNG, JPG)
- [x] Store uploaded files in MinIO with structured key naming (tenant/doc-id)
- [x] Add OCR service integration (Tesseract, Textract, or containerized OCR)
- [x] Implement POST /documents/{id}/extract to return parsed text and metadata
- [x] Add AI utility endpoints (summarize, classify, chunk preview)
- [x] Add Dockerfile and register fastapi service in docker-compose
- [x] Document all endpoints in OpenAPI/Swagger UI
- [x] Write pytest coverage for upload, storage, and extraction flows
- [x] Verify end-to-end: upload sample PDF, extract text, confirm MinIO object exists

**Exit criteria:** Documents can be uploaded, stored, and text-extracted via API.

---

## Phase 4 — RAG Pipeline

*Embeddings, Qdrant indexing, retrieval, and grounded generation* · **0/10 Pending**

- [ ] Define chunking strategy (size, overlap) and metadata schema
- [ ] Implement embedding generation via Bedrock embedding model
- [ ] Build indexing pipeline: chunk → embed → upsert into Qdrant collection
- [ ] Implement similarity search with top-k retrieval and score threshold
- [ ] Build RAG orchestrator: retrieve context → assemble prompt → call Nova Lite
- [ ] Return source citations (document ID, chunk, page) in API response
- [ ] Trigger indexing automatically after document extraction (Phase 3 hook)
- [ ] Expose POST /rag/query endpoint with streaming or JSON response
- [ ] Create golden-set test questions with expected source documents
- [ ] Verify end-to-end: ingest doc → query → grounded answer with citations

**Exit criteria:** Questions return answers grounded in uploaded documents with traceable sources.

---

## Phase 5 — Multi-Agent n8n Workflows

*Email automation, document analysis, approvals, Slack notifications* · **0/10 Pending**

- [ ] Configure n8n credentials for Spring API, FastAPI, email, and Slack
- [ ] Build document intake workflow: upload trigger → extract → index → notify
- [ ] Build document analysis agent workflow using RAG query + structured output
- [ ] Build email automation workflow (parse inbound, classify, route to agent)
- [ ] Add human approval gate with wait/resume node before sensitive actions
- [ ] Send Slack notifications on completion, errors, and approval requests
- [ ] Add error handling branches and retry logic across all workflows
- [ ] Expose webhook triggers from Spring/FastAPI to kick off n8n workflows
- [ ] Create end-to-end demo scenario with sample documents and email thread
- [ ] Document workflow diagrams, env setup, and runbook for each automation

**Exit criteria:** A full agentic workflow runs from trigger → analysis → approval → notification.

---

## Suggested approach

Work through **one phase at a time**. Finish all items in the current phase before starting the next — later phases depend on earlier infrastructure and APIs.

**Next up:** Phase 4 (RAG Pipeline).
