"""FastAPI entrypoint — Phase 3 document ingestion service."""

from fastapi import FastAPI

from app.config import get_settings
from app.routers import ai_utils, documents
from app.schemas import HealthResponse

settings = get_settings()

tags_metadata = [
    {
        "name": "documents",
        "description": (
            "Upload documents to MinIO and extract their text — embedded PDF text "
            "where available, Tesseract OCR as a fallback for scanned pages/images."
        ),
    },
    {
        "name": "ai-utilities",
        "description": (
            "Local, deterministic text utilities — summarize, classify, and preview "
            "RAG-style chunks. No Bedrock/Spring AI dependency; each endpoint accepts "
            "either pasted `text` or a previously-uploaded `document_id`."
        ),
    },
    {
        "name": "ops",
        "description": "Operational endpoints for local runs and container health checks.",
    },
]

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Document upload, OCR, and AI utility endpoints (Phase 3).",
    openapi_tags=tags_metadata,
)

app.include_router(documents.router)
app.include_router(ai_utils.router)


@app.get(
    "/health",
    tags=["ops"],
    response_model=HealthResponse,
    summary="Liveness check",
    response_description="Process status and build info",
)
def health() -> HealthResponse:
    """Liveness probe for local runs and Docker's HEALTHCHECK. Always returns
    200 if the process is up — it does not check MinIO/Tesseract reachability,
    since those are checked lazily per-request (see /documents/upload).
    """
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
