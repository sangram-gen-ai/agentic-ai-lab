# FastAPI Service (Phase 3)

Document ingestion and AI utility service.

## Planned responsibilities

- `POST /documents/upload` — store files in MinIO (`minio:9000`)
- `POST /documents/{id}/extract` — OCR and text extraction
- Read sample files from `../../documents/{resumes,invoices,contracts,healthcare,claims}/`
- AI utility endpoints (summarize, classify, chunk preview)

## Scaffold checklist

- [ ] Initialize FastAPI project with uvicorn
- [ ] Add MinIO and Qdrant clients (internal hostnames)
- [ ] Add `Dockerfile`
- [ ] Uncomment `fast-api` service in `docker-compose.yml`
