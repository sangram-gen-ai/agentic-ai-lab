"""Request / response models for the FastAPI service."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UploadResponse(BaseModel):
    """Returned after a file is validated and stored in MinIO."""

    document_id: str = Field(description="Server-assigned ID used in later extract/RAG calls")
    tenant_id: str = Field(description="Logical tenant / namespace for the document")
    filename: str = Field(description="Original filename, as sent by the client")
    content_type: str = Field(description="Canonical content type inferred from the file signature")
    size_bytes: int = Field(description="Size of the stored file in bytes")
    bucket: str = Field(description="MinIO bucket name")
    object_key: str = Field(description="MinIO object key: {tenant}/{document_id}/{filename}")
    status: str = Field(description="stored when the object was written to MinIO")
    storage: str = Field(description="Where bytes live: minio")


class ExtractPage(BaseModel):
    """One page's extracted text and the method used to get it."""

    page_number: int = Field(description="1-indexed page number")
    text: str = Field(description="Extracted text for this page")
    method: str = Field(description="pdf-text | tesseract")


class ExtractResponse(BaseModel):
    """Parsed text + metadata from OCR / PDF text extraction."""

    document_id: str = Field(description="The document that was extracted")
    tenant_id: str = Field(description="Tenant the document was uploaded under")
    filename: str = Field(description="Original filename")
    content_type: str = Field(description="Content type of the stored document")
    bucket: str = Field(description="MinIO bucket name")
    object_key: str = Field(description="MinIO object key the bytes were loaded from")
    engine: str = Field(description="pdf-text | tesseract | pdf-text+tesseract")
    language: str = Field(description="Tesseract language code used for any OCR pages")
    page_count: int = Field(description="Number of pages extracted")
    char_count: int = Field(description="Length of the combined `text` field, in characters")
    text: str = Field(description="All pages' text joined together")
    pages: list[ExtractPage] = Field(description="Per-page breakdown of text and extraction method")


class TextInput(BaseModel):
    """Shared input: paste text, or point at a stored document."""

    text: str | None = Field(default=None, description="Raw text to process")
    document_id: str | None = Field(
        default=None,
        description="Stored document to load + extract (used only when 'text' is omitted)",
    )
    tenant_id: str = Field(
        default="default",
        description="Tenant the document was uploaded under (only relevant with document_id)",
    )

    @model_validator(mode="after")
    def require_text_or_document(self) -> "TextInput":
        has_text = bool(self.text and self.text.strip())
        has_doc = bool(self.document_id and self.document_id.strip())
        if not has_text and not has_doc:
            raise ValueError("Provide either non-empty 'text' or a 'document_id'.")
        return self


class SummarizeRequest(TextInput):
    max_sentences: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Cap on sentences returned. Defaults to the configured value (3) if omitted.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": (
                        "The quick brown fox jumps over the lazy dog. This sentence is filler. "
                        "Machine learning models can summarize documents efficiently. "
                        "Another filler sentence goes here for length."
                    ),
                    "max_sentences": 2,
                }
            ]
        }
    )


class SummarizeResponse(BaseModel):
    summary: str = Field(description="The extractive summary — a subset of the original sentences")
    sentence_count: int = Field(description="Number of sentences included in the summary")
    method: str = Field(description="Always 'extractive' for now (top-scoring sentences)")
    document_id: str | None = Field(
        default=None, description="Echoes the input document_id, if one was used"
    )
    char_count: int = Field(description="Length of the input text that was summarized")


class ClassifyRequest(TextInput):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"text": "Invoice total due is one hundred dollars. Please remit payment."}
            ]
        }
    )


class ClassifyResponse(BaseModel):
    label: str = Field(
        description="Best-matching category: resume | invoice | contract | healthcare | claim | unknown"
    )
    confidence: float = Field(description="Score of the winning label, 0.0-1.0")
    scores: dict[str, float] = Field(description="Score for every category, for transparency")
    method: str = Field(description="Always 'keyword' for now (keyword-overlap heuristic)")
    document_id: str | None = Field(
        default=None, description="Echoes the input document_id, if one was used"
    )


class ChunkRequest(TextInput):
    chunk_size: int | None = Field(
        default=None,
        ge=1,
        le=10_000,
        description="Characters per chunk. Defaults to the configured value (500) if omitted.",
    )
    chunk_overlap: int | None = Field(
        default=None,
        ge=0,
        le=9_999,
        description=(
            "Characters shared between consecutive chunks. Must be smaller than chunk_size. "
            "Defaults to the configured value (50) if omitted."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"text": "abcdefghijklmnopqrstuvwxyz", "chunk_size": 10, "chunk_overlap": 3}
            ]
        }
    )


class TextChunkModel(BaseModel):
    """One sliding-window chunk of the source text."""

    index: int = Field(description="0-indexed chunk position")
    text: str = Field(description="The chunk's text")
    start: int = Field(description="Start offset in the source text (inclusive)")
    end: int = Field(description="End offset in the source text (exclusive)")
    char_count: int = Field(description="Length of this chunk, in characters")


class ChunkPreviewResponse(BaseModel):
    document_id: str | None = Field(
        default=None, description="Echoes the input document_id, if one was used"
    )
    chunk_count: int = Field(description="Number of chunks produced")
    chunk_size: int = Field(description="Chunk size actually used (request value or the default)")
    chunk_overlap: int = Field(
        description="Chunk overlap actually used (request value or the default)"
    )
    chunks: list[TextChunkModel] = Field(description="The chunks, in order")


class ErrorResponse(BaseModel):
    detail: str = Field(description="Human-readable explanation of what went wrong")


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' when the process is up and serving requests")
    service: str = Field(description="Application name")
    version: str = Field(description="Application version")
    environment: str = Field(description="Deployment environment, e.g. 'local'")
