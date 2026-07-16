# End-to-End — All Phases Sequence Diagram

> Companion to [`phase-checklist.md`](./phase-checklist.md) and
> [`architecture.md`](./architecture.md). Shows the **target** happy path once
> Phases 1–5 are complete. Phases 1–2 are implemented today; 3–5 are planned
> (shown as the intended orchestration).

One story: a user submits a document through n8n → FastAPI stores and extracts
text → RAG indexes into Qdrant → an agent asks a grounded question via Spring AI /
Bedrock → a human approves → Email/Slack notify. Phase 1 infrastructure is the
shared foundation underneath every hop.

## Visual (PNG)

![End-to-end all-phases sequence](./end-to-end-sequence-diagram.png)

*Source Mermaid: [`end-to-end-sequence-diagram.mmd`](./end-to-end-sequence-diagram.mmd) · Rendered at 1568×1084*

## Mermaid source

```mermaid
sequenceDiagram
    actor User
    participant N8N as n8n
    participant FastAPI as fast-api
    participant MinIO
    participant OCR as OCR Service
    participant Qdrant
    participant Spring as spring-ai
    participant Redis
    participant PG as PostgreSQL
    participant Bedrock as AWS Bedrock<br/>Nova Lite
    actor Approver as Human Approver
    participant Notify as Email / Slack

    Note over User,Notify: Phase 1 — Shared infrastructure already running<br/>(Postgres, Redis, Qdrant, MinIO, n8n on agentic-ai-network)

    Note over User,Notify: Phase 5 trigger + Phase 3 ingestion
    User->>N8N: Upload document / webhook / email inbound
    N8N->>FastAPI: POST /documents/upload
    FastAPI->>MinIO: PUT object tenant/{docId}
    MinIO-->>FastAPI: stored
    FastAPI-->>N8N: docId

    N8N->>FastAPI: POST /documents/{docId}/extract
    FastAPI->>MinIO: GET object
    MinIO-->>FastAPI: bytes
    FastAPI->>OCR: extract text (PDF / image)
    OCR-->>FastAPI: text + metadata
    FastAPI-->>N8N: extracted text

    Note over User,Notify: Phase 4 — Index for RAG
    N8N->>FastAPI: trigger index (or FastAPI auto-hook after extract)
    FastAPI->>FastAPI: chunk text (size / overlap)
    FastAPI->>Bedrock: embed chunks
    Bedrock-->>FastAPI: vectors
    FastAPI->>Qdrant: upsert collection + metadata (docId, page, chunk)
    Qdrant-->>FastAPI: indexed
    FastAPI-->>N8N: index OK

    Note over User,Notify: Phase 5 analysis agent + Phase 4 RAG + Phase 2 Spring AI
    N8N->>Spring: POST /rag/query (or /api/v1/chat with retrieved context)
    Spring->>Redis: rate limit (client IP) + optional session
    Redis-->>Spring: allow
    Spring->>Qdrant: similarity search top-k
    Qdrant-->>Spring: chunks + scores + citations
    Spring->>Bedrock: Converse (Nova Lite + grounded context)
    Bedrock-->>Spring: answer + reasoning
    Spring->>Redis: append session history
    Spring-)PG: @Async audit log (schema spring_ai)
    Spring-->>N8N: grounded answer + citations

    Note over User,Notify: Phase 5 — Human-in-the-loop + notifications
    N8N->>Approver: wait node — approve sensitive action?
    Approver-->>N8N: approve / reject
    alt approved
        N8N->>Notify: Email + Slack (result, citations, docId)
        Notify-->>User: notification delivered
        N8N->>PG: persist workflow execution (n8n public schema)
    else rejected
        N8N->>Notify: Slack — approval denied / needs revision
    end

    Note over User,Notify: Alternate Phase 2 path (direct chat, no document)<br/>User → spring-ai /api/v1/chat → Redis → Bedrock → Postgres audit
```

## How phases map onto the flow

| Step in the diagram | Phase | Status |
|---------------------|-------|--------|
| Infra up (Postgres, Redis, Qdrant, MinIO, n8n) | 1 | Done |
| `spring-ai` chat, Redis session/rate limit, Postgres audit, Bedrock | 2 | Done |
| Upload → MinIO → OCR extract | 3 | Planned |
| Chunk → embed → Qdrant → RAG query + citations | 4 | Planned |
| n8n orchestration, approval gate, Email/Slack | 5 | Planned |

## Notes

- **n8n is the Phase 5 conductor** — it does not replace Spring AI or FastAPI; it calls them over `agentic-ai-network` (`http://spring-ai:8080`, `http://fast-api:8000`).
- **Two Postgres “lanes”:** n8n owns workflow tables in schema `public`; Spring AI owns `spring_ai.chat_audit_log` for chat/RAG audit.
- **Redis** is used by Spring AI (Phase 2+) for session cache and rate limiting; n8n may also use it later for queues/rate limits.
- **Qdrant + MinIO** are provisioned in Phase 1 but first consumed in Phases 3–4.
- Phases 3–5 boxes are **target design** from the checklist/architecture — wire them as you implement each phase.

## Related diagrams

| Diagram | Scope |
|---------|--------|
| [`phase-1-sequence-diagram.md`](./phase-1-sequence-diagram.md) | Compose startup / healthchecks |
| [`phase-2-sequence-diagram.md`](./phase-2-sequence-diagram.md) | Chat request path in detail |
| [`architecture.md`](./architecture.md) | Component layer overview |
