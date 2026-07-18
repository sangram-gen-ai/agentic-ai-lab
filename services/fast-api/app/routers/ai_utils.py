"""AI utility endpoints — summarize, classify, chunk preview."""

from fastapi import APIRouter, HTTPException, status

from app.schemas import (
    ChunkPreviewResponse,
    ChunkRequest,
    ClassifyRequest,
    ClassifyResponse,
    ErrorResponse,
    SummarizeRequest,
    SummarizeResponse,
    TextChunkModel,
)
from app.services.ai_utils import get_ai_utils_service
from app.services.text_source import resolve_text_async

router = APIRouter(prefix="/ai", tags=["ai-utilities"])


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Extractive summary of text or a stored document",
    response_description="The extractive summary plus sentence/char counts",
)
async def summarize(body: SummarizeRequest) -> SummarizeResponse:
    """Pick the top-scoring sentences (by shared-word frequency, with a slight
    lead-sentence bias) from either the pasted `text` or a stored document's
    OCR/PDF-extracted text. Purely local — no LLM call.
    """
    text, doc_id = await resolve_text_async(body)
    result = get_ai_utils_service().summarize(text, max_sentences=body.max_sentences)
    return SummarizeResponse(
        summary=result.summary,
        sentence_count=result.sentence_count,
        method=result.method,
        document_id=doc_id,
        char_count=len(text),
    )


@router.post(
    "/classify",
    response_model=ClassifyResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Classify text into a document category",
    response_description="The winning label, its confidence, and every category's score",
)
async def classify(body: ClassifyRequest) -> ClassifyResponse:
    """Score the text against keyword lists for each category (resume, invoice,
    contract, healthcare, claim) and return the best match, or "unknown" if
    nothing scores above zero. Purely local keyword matching — no LLM call.
    """
    text, doc_id = await resolve_text_async(body)
    result = get_ai_utils_service().classify(text)
    return ClassifyResponse(
        label=result.label,
        confidence=result.confidence,
        scores=result.scores,
        method=result.method,
        document_id=doc_id,
    )


@router.post(
    "/chunk",
    response_model=ChunkPreviewResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Preview text chunks (size + overlap) for RAG",
    response_description="The resulting chunks, with each one's offsets in the source text",
)
async def chunk_preview(body: ChunkRequest) -> ChunkPreviewResponse:
    """Split text into overlapping, fixed-size windows — the same chunking
    strategy Phase 4's RAG pipeline will use for embedding/indexing. Lets you
    preview and tune chunk_size/chunk_overlap before that pipeline exists.
    """
    text, doc_id = await resolve_text_async(body)
    try:
        result = get_ai_utils_service().chunk(
            text,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ChunkPreviewResponse(
        document_id=doc_id,
        chunk_count=result.chunk_count,
        chunk_size=result.chunk_size,
        chunk_overlap=result.chunk_overlap,
        chunks=[
            TextChunkModel(
                index=c.index,
                text=c.text,
                start=c.start,
                end=c.end,
                char_count=c.char_count,
            )
            for c in result.chunks
        ],
    )
