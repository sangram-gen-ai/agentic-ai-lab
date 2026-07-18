"""Validate uploaded documents by extension, Content-Type, and magic bytes."""

from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status

# extension → (canonical content-type, magic-byte prefixes)
ALLOWED_TYPES: dict[str, tuple[str, tuple[bytes, ...]]] = {
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
}

ALLOWED_CONTENT_TYPES = {meta[0] for meta in ALLOWED_TYPES.values()}


@dataclass(frozen=True)
class ValidatedFile:
    filename: str
    content_type: str
    content: bytes
    size_bytes: int


def _extension(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


_CHUNK_SIZE = 1024 * 1024  # 1 MiB


async def read_upload_within_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Read the upload in bounded chunks, aborting with 413 as soon as it's over
    limit — instead of buffering an arbitrarily large body before checking size.
    """
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds max size of {max_bytes} bytes.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


_PATH_TRAVERSAL_SEGMENTS = {".", ".."}
_PATH_SEPARATORS = ("/", "\\")


def sanitize_path_segment(value: str, *, field_name: str) -> str:
    """Reject values unsafe for use as a MinIO/S3 object key path segment.

    Blocks path separators, null bytes, and the literal "."/".." segments —
    the actual traversal vectors — without over-restricting otherwise-normal
    filenames (spaces, parentheses, unicode, etc. are all fine).
    """
    if not value or value in _PATH_TRAVERSAL_SEGMENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}: must not be empty, '.', or '..'.",
        )
    if "\x00" in value or any(sep in value for sep in _PATH_SEPARATORS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} '{value}': path separators are not allowed.",
        )
    return value


def sanitize_tenant_id(tenant_id: str) -> str:
    """Normalize (strip, default to "default") and validate a tenant_id for
    use as a MinIO key path segment. Shared by every call site that accepts
    a caller-supplied tenant_id, so the default/sanitize behavior can't drift.
    """
    return sanitize_path_segment(tenant_id.strip() or "default", field_name="tenant_id")


def validate_upload(file: UploadFile, content: bytes, max_bytes: int) -> ValidatedFile:
    """Reject unsupported or oversized uploads with a clear 4xx error."""
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds max size of {max_bytes} bytes.",
        )

    ext = _extension(file.filename)
    if ext not in ALLOWED_TYPES:
        allowed = ", ".join(sorted(ALLOWED_TYPES))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file extension '{ext or '(none)'}'. Allowed: {allowed}",
        )

    expected_type, magic_prefixes = ALLOWED_TYPES[ext]
    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared and declared not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported Content-Type '{file.content_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            ),
        )
    if declared and declared != expected_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Content-Type '{declared}' does not match extension '{ext}' "
                f"(expected '{expected_type}')."
            ),
        )

    if not any(content.startswith(prefix) for prefix in magic_prefixes):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File content does not match a valid {expected_type} signature "
                f"(possible renamed or corrupt file)."
            ),
        )

    return ValidatedFile(
        filename=file.filename or f"upload{ext}",
        content_type=expected_type,
        content=content,
        size_bytes=len(content),
    )
