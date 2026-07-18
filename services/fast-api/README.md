# FastAPI Service (Phase 3)

Document ingestion and AI utility service.

## Current status

| Step | Status |
|------|--------|
| 1. Bootstrap + `/health` | Done |
| 2. `POST /documents/upload` | Done |
| 3. MinIO storage | Done |
| 4. OCR integration | Done |
| 5. `POST /documents/{id}/extract` | Done |
| 6. AI utility endpoints | Done |
| 7. Dockerfile + compose | Done |
| 8. OpenAPI polish | Done |
| 9. pytest coverage | Done |
| 10. End-to-end verify | Done |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/documents/upload` | Upload PDF / PNG / JPG → MinIO |
| `POST` | `/documents/{id}/extract` | Extract text (OCR / PDF text layer) |
| `POST` | `/ai/summarize` | Extractive summary |
| `POST` | `/ai/classify` | Keyword category label |
| `POST` | `/ai/chunk` | Chunk preview (size + overlap) |
| `GET` | `/docs` | Swagger UI |

### AI utilities (Step 6)

Local, deterministic helpers — **no Bedrock / Spring AI required**. Body accepts either pasted `text` or a stored `document_id` (+ `tenant_id`).

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/ai/summarize` | Extractive | Top sentences by word frequency (default 3) |
| `/ai/classify` | Keyword | Labels: `resume`, `invoice`, `contract`, `healthcare`, `claim`, `unknown` |
| `/ai/chunk` | Sliding window | Defaults: size `500`, overlap `50` (Phase 4 RAG preview) |

```bash
curl -s -X POST http://localhost:8000/ai/classify \
  -H 'Content-Type: application/json' \
  -d '{"text":"Invoice total due is one hundred dollars. Please remit payment."}'

curl -s -X POST http://localhost:8000/ai/chunk \
  -H 'Content-Type: application/json' \
  -d '{"text":"'"$(python -c 'print("word "*200)')"'","chunk_size":80,"chunk_overlap":20}'
```

## Run locally (without Docker)

```bash
cd services/fast-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Requires MinIO (`docker compose up -d minio minio-init`) and Tesseract on PATH (`brew install tesseract`) for OCR/extract.

## Docker (Step 7, recommended)

```bash
docker compose up -d --build fast-api
docker compose logs -f fast-api
```

The image (Debian-based `python:3.14-slim`) installs `tesseract-ocr` via apt so
OCR works out of the box — no host Tesseract needed. `MINIO_ENDPOINT` in the
root `.env` must point at the container-internal address (`http://minio:9000`,
not `localhost`) — `fast-api`'s own default is localhost-oriented, which only
works for the non-Docker run above.

Open Swagger: http://localhost:8000/docs

## Tests (Step 9)

```bash
cd services/fast-api
pip install -r requirements-dev.txt
pytest
```

- `test_file_validation.py`, `test_ai_utils_service.py`, `test_ocr.py` — pure logic, no external services (OCR tests use the real local Tesseract/PyMuPDF install, not mocks).
- `test_minio_storage.py` — mocks the `minio` client to verify connection-failure/malformed-key exceptions translate into clean HTTP errors (503/404) instead of leaking as 500 — the bug class found in Steps 3 and 6.
- `test_document_store.py` — uses an in-memory fake storage. Includes the regression coverage for the Step 5 tenant-isolation bug (a cached document must still 404 for the wrong tenant_id).
- `test_routers_documents.py`, `test_routers_ai_utils.py` — full HTTP request/response tests against the real MinIO + Tesseract stack. **Skip automatically** (not fail) if MinIO isn't reachable, so `pytest` still runs the rest of the suite without Docker.

## Project layout

```
services/fast-api/
├── app/
│   ├── config.py
│   ├── main.py
│   ├── schemas.py
│   ├── routers/
│   │   ├── documents.py          # upload + extract
│   │   └── ai_utils.py           # summarize / classify / chunk
│   └── services/
│       ├── file_validation.py
│       ├── minio_storage.py
│       ├── document_store.py
│       ├── ocr.py
│       ├── ai_utils.py
│       └── text_source.py        # text vs document_id resolver
├── tests/
│   ├── conftest.py                # fixtures: TestClient, sample files, MinIO skip
│   ├── test_file_validation.py
│   ├── test_ai_utils_service.py
│   ├── test_ocr.py
│   ├── test_minio_storage.py
│   ├── test_document_store.py
│   ├── test_routers_documents.py
│   └── test_routers_ai_utils.py
├── requirements.txt
├── requirements-dev.txt           # + pytest, httpx
├── pytest.ini
├── Dockerfile                      # python:3.14-slim + tesseract-ocr
├── .dockerignore
├── .gitignore
└── README.md
```

## OpenAPI docs (Step 8)

`/docs` is fully documented: tag descriptions for `documents`/`ai-utilities`/`ops`,
a docstring + `response_description` on every endpoint, `Field(description=...)`
on every request/response field, and pre-filled request examples on
`SummarizeRequest`/`ClassifyRequest`/`ChunkRequest` so Swagger's "Try it out"
works without reading the source first. `/health` now has a real `HealthResponse`
model instead of an untyped dict.

## End-to-end verification (Step 10)

Verified against the full `docker compose up -d` stack (not just this service
in isolation) with real, multi-sentence sample documents (not the minimal
pytest fixtures):

1. **Upload** a realistic invoice PDF (embedded text layer) → `POST /documents/upload`
2. **Extract** → `POST /documents/{id}/extract` returns the complete, correctly
   wrapped text (`engine: "pdf-text"`)
3. **Confirm MinIO** — `mc ls --recursive` on the real bucket shows both the
   file and its `.meta.json` sidecar for every uploaded document
4. **AI utilities** — `/ai/summarize`, `/ai/classify` (correctly labeled
   `invoice`), and `/ai/chunk` all run successfully against the extracted text
5. **OCR path** — also verified with a PNG and a scanned-image-only PDF;
   both correctly report `engine: "tesseract"` with real Tesseract output

Phase 3 is now feature-complete (10/10).

## Phase 4 (next)

RAG pipeline: embeddings, Qdrant indexing, and retrieval-augmented generation
— building on this service's `/documents/upload` (MinIO storage) and
`/ai/chunk` (chunking preview) as the ingestion front end.
