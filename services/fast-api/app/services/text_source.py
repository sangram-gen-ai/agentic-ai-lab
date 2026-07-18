"""Resolve a stored document into text, shared by the extract endpoint and
the AI-utils endpoints (summarize/classify/chunk).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.schemas import TextInput
from app.services.document_store import StoredDocument, document_store
from app.services.file_validation import sanitize_path_segment, sanitize_tenant_id
from app.services.ocr import OcrResult, get_ocr_service


def load_and_extract(document_id: str, tenant_id: str) -> tuple[StoredDocument, OcrResult]:
    """Resolve a stored document, load its bytes, and run OCR/text extraction.

    The one place that does "resolve -> load bytes -> OCR" — both
    ``POST /documents/{id}/extract`` and the AI-utils document_id path call
    this instead of each reimplementing the sequence.
    """
    safe_tenant_id = sanitize_tenant_id(tenant_id)
    safe_document_id = sanitize_path_segment(document_id, field_name="document_id")

    doc, content = document_store.resolve_and_load(safe_document_id, safe_tenant_id)
    result = get_ocr_service().extract(content, doc.content_type)
    if not result.text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Document '{document_id}' produced no extractable text.",
        )
    return doc, result


def resolve_text(
    *,
    text: str | None,
    document_id: str | None,
    tenant_id: str,
) -> tuple[str, str | None]:
    """Return ``(text, document_id_or_none)``.

    Prefer explicit ``text``. Otherwise load + OCR the stored document.
    """
    if text is not None and text.strip():
        return text.strip(), document_id

    if not document_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either non-empty 'text' or a 'document_id'.",
        )

    doc, result = load_and_extract(document_id, tenant_id)
    return result.text, doc.document_id


async def resolve_text_async(body: TextInput) -> tuple[str, str | None]:
    """Async wrapper for resolve_text — offloads the blocking MinIO/OCR work
    without stalling the event loop, same as the /extract endpoint does.
    Takes the request body directly so callers don't repeat its 3 fields.
    """
    return await run_in_threadpool(
        resolve_text,
        text=body.text,
        document_id=body.document_id,
        tenant_id=body.tenant_id,
    )
