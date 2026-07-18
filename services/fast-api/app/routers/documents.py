"""Document upload and extract endpoints."""

from fastapi import APIRouter, File, Form, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.schemas import ErrorResponse, ExtractPage, ExtractResponse, UploadResponse
from app.services.document_store import document_store
from app.services.file_validation import (
    read_upload_within_limit,
    sanitize_path_segment,
    sanitize_tenant_id,
    validate_upload,
)
from app.services.text_source import load_and_extract

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="Upload a document (PDF, PNG, or JPG)",
    response_description="The stored document's ID, MinIO location, and metadata",
)
async def upload_document(
    file: UploadFile = File(..., description="PDF, PNG, or JPG file"),
    tenant_id: str = Form(
        default="default",
        description="Logical tenant / namespace used in the MinIO object key path",
    ),
) -> UploadResponse:
    """Validate the file (extension + Content-Type + magic bytes must all
    agree), store it in MinIO under `{tenant_id}/{document_id}/{filename}`,
    and write a `.meta.json` sidecar so it can still be resolved after a
    process restart. Returns the generated `document_id` used by
    `/documents/{id}/extract` and the `/ai/*` endpoints.
    """
    settings = get_settings()
    content = await read_upload_within_limit(file, max_bytes=settings.max_upload_bytes)
    validated = validate_upload(file, content, max_bytes=settings.max_upload_bytes)

    safe_tenant_id = sanitize_tenant_id(tenant_id)
    safe_filename = sanitize_path_segment(validated.filename, field_name="filename")

    # document_store.save() talks to MinIO with the synchronous minio client —
    # run it in a worker thread so a slow/blocked MinIO call doesn't stall the
    # event loop for every other concurrent request (including /health).
    stored = await run_in_threadpool(
        document_store.save,
        tenant_id=safe_tenant_id,
        filename=safe_filename,
        content_type=validated.content_type,
        content=validated.content,
    )

    return UploadResponse(
        document_id=stored.document_id,
        tenant_id=stored.tenant_id,
        filename=stored.filename,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        bucket=stored.bucket,
        object_key=stored.object_key,
        status="stored",
        storage="minio",
    )


@router.post(
    "/{document_id}/extract",
    response_model=ExtractResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="Extract text from a stored document",
    response_description="Extracted text (combined and per-page), plus which engine produced it",
)
async def extract_document(
    document_id: str,
    tenant_id: str = Query(
        default="default",
        description="Tenant used when the document was uploaded (needed after restart)",
    ),
) -> ExtractResponse:
    """Load the document's bytes from MinIO and extract its text: PDFs use
    the embedded text layer where present, falling back to rendering +
    Tesseract OCR for scanned/image-only pages; images always go through
    Tesseract. `tenant_id` must match the one used at upload time.
    """
    doc, result = await run_in_threadpool(load_and_extract, document_id, tenant_id)

    return ExtractResponse(
        document_id=doc.document_id,
        tenant_id=doc.tenant_id,
        filename=doc.filename,
        content_type=doc.content_type,
        bucket=doc.bucket,
        object_key=doc.object_key,
        engine=result.engine,
        language=result.language,
        page_count=result.page_count,
        char_count=result.char_count,
        text=result.text,
        pages=[
            ExtractPage(page_number=p.page_number, text=p.text, method=p.method)
            for p in result.pages
        ],
    )
