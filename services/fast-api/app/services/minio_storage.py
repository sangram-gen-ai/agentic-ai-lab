"""MinIO (S3-compatible) object storage for uploaded documents."""

from __future__ import annotations

from functools import lru_cache, wraps
from io import BytesIO
from urllib.parse import urlparse

from fastapi import HTTPException, status
from minio import Minio
from minio.error import S3Error

from app.config import Settings, get_settings


def build_object_key(tenant_id: str, document_id: str, filename: str) -> str:
    """Structured key: {tenant_id}/{document_id}/{filename}."""
    return f"{tenant_id}/{document_id}/{filename}"


def build_meta_key(tenant_id: str, document_id: str) -> str:
    """Sidecar metadata key written next to the uploaded file."""
    return f"{tenant_id}/{document_id}/.meta.json"


def _translate_connection_errors(func):
    """The minio SDK raises non-S3Error exceptions too: urllib3 exceptions for
    connectivity failures, plain ValueError for a malformed object key (e.g. a
    "." or ".." path segment). Neither is caught by an `except S3Error`, so
    every method would otherwise need to remember its own generic fallback.
    Each method still handles S3Error itself, since the right status/detail
    for an S3 API error varies (404 vs 503, different messages).
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (S3Error, HTTPException):
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"MinIO is unreachable: {exc}",
            ) from exc

    return wrapper


class MinioStorage:
    """Thin wrapper around the MinIO Python client."""

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.minio_bucket_documents
        self._client = self._build_client(settings)
        self._ensure_bucket()

    @staticmethod
    def _build_client(settings: Settings) -> Minio:
        parsed = urlparse(settings.minio_endpoint)
        endpoint = parsed.netloc or parsed.path
        if not endpoint:
            raise ValueError(f"Invalid MINIO_ENDPOINT: {settings.minio_endpoint!r}")
        return Minio(
            endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=parsed.scheme == "https",
        )

    @_translate_connection_errors
    def _ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        except S3Error as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"MinIO bucket check failed: {exc.code}",
            ) from exc

    @_translate_connection_errors
    def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        try:
            self._client.put_object(
                bucket_name=self._bucket,
                object_name=object_key,
                data=BytesIO(content),
                length=len(content),
                content_type=content_type,
            )
        except S3Error as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to store object in MinIO: {exc.code}",
            ) from exc

    @_translate_connection_errors
    def get(self, object_key: str) -> bytes:
        try:
            response = self._client.get_object(self._bucket, object_key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Object not found: {object_key}",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to read object from MinIO: {exc.code}",
            ) from exc

    @_translate_connection_errors
    def exists(self, object_key: str) -> bool:
        try:
            self._client.stat_object(self._bucket, object_key)
            return True
        except S3Error:
            return False

    @property
    def bucket(self) -> str:
        return self._bucket


@lru_cache
def get_minio_storage() -> MinioStorage:
    return MinioStorage(get_settings())
