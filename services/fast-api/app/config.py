"""Application settings loaded from environment variables / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central config for the FastAPI service.

    Values come from environment variables (docker-compose `.env`) or a local
    `.env` file when running on the host. Defaults are safe for local Mac use.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agentic AI FastAPI"
    app_version: str = "0.1.0"
    environment: str = "local"

    # Host bind — 0.0.0.0 so Docker and local uvicorn both work
    host: str = "0.0.0.0"
    port: int = 8000

    # Upload limits (Step 2) — default 20 MiB
    max_upload_bytes: int = 20 * 1024 * 1024

    # OCR (Step 4) — requires system Tesseract (`brew install tesseract`)
    ocr_language: str = "eng"
    # If a PDF page has fewer chars than this, render it and run Tesseract
    ocr_pdf_min_chars_per_page: int = 40
    # Optional override; leave empty to use PATH / pytesseract default
    tesseract_cmd: str = ""

    # AI utilities (Step 6) — local extractive/heuristic helpers (no Bedrock required)
    chunk_size: int = 500
    chunk_overlap: int = 50
    summarize_max_sentences: int = 3

    # Phase 1 infra (used in later steps; defined early so settings stay in one place)
    minio_endpoint: str = "http://localhost:9000"
    minio_root_user: str = "agentic_minio"
    minio_root_password: str = "change_me_minio"
    minio_bucket_documents: str = "documents"

    qdrant_url: str = "http://localhost:6333"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — one parse per process."""
    return Settings()
