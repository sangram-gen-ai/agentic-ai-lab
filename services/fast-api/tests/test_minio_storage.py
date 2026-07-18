"""Tests for MinioStorage's exception translation — mocks the underlying
`minio.Minio` client so no real MinIO server is needed. Covers the exact bug
class found across Steps 3 and 6: the SDK raises non-S3Error exceptions
(urllib3 connectivity errors, ValueError for a malformed object key) that
must still translate into a clean HTTP response, not leak as a 500.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from minio.error import S3Error

from app.services.minio_storage import (
    MinioStorage,
    build_meta_key,
    build_object_key,
)


def _s3_error(code: str) -> S3Error:
    return S3Error(
        response=None,
        code=code,
        message="simulated",
        resource="/bucket/key",
        request_id="req-1",
        host_id="host-1",
    )


@pytest.fixture()
def storage() -> MinioStorage:
    """A MinioStorage with its client swapped for a mock — bypasses the real
    __init__ (which would try to reach a real server) via __new__.
    """
    instance = MinioStorage.__new__(MinioStorage)
    instance._bucket = "test-bucket"
    instance._client = MagicMock()
    return instance


class TestBuildKeys:
    def test_object_key_format(self):
        assert build_object_key("tenant", "doc-1", "file.pdf") == "tenant/doc-1/file.pdf"

    def test_meta_key_format(self):
        assert build_meta_key("tenant", "doc-1") == "tenant/doc-1/.meta.json"


class TestPut:
    def test_put_success(self, storage: MinioStorage):
        storage.put(object_key="k", content=b"data", content_type="application/pdf")
        storage._client.put_object.assert_called_once()

    def test_put_s3_error_returns_503(self, storage: MinioStorage):
        storage._client.put_object.side_effect = _s3_error("InternalError")
        with pytest.raises(HTTPException) as exc_info:
            storage.put(object_key="k", content=b"data", content_type="application/pdf")
        assert exc_info.value.status_code == 503

    def test_put_connectivity_failure_returns_503_not_500(self, storage: MinioStorage):
        """The regression case: a non-S3Error (e.g. urllib3 MaxRetryError when
        MinIO is unreachable) must still become a clean 503.
        """
        storage._client.put_object.side_effect = ConnectionError("connection refused")
        with pytest.raises(HTTPException) as exc_info:
            storage.put(object_key="k", content=b"data", content_type="application/pdf")
        assert exc_info.value.status_code == 503


class TestGet:
    def test_get_success_reads_and_releases_response(self, storage: MinioStorage):
        response = MagicMock()
        response.read.return_value = b"content"
        storage._client.get_object.return_value = response

        result = storage.get("k")

        assert result == b"content"
        response.close.assert_called_once()
        response.release_conn.assert_called_once()

    def test_get_missing_object_returns_404(self, storage: MinioStorage):
        storage._client.get_object.side_effect = _s3_error("NoSuchKey")
        with pytest.raises(HTTPException) as exc_info:
            storage.get("k")
        assert exc_info.value.status_code == 404

    def test_get_other_s3_error_returns_503(self, storage: MinioStorage):
        storage._client.get_object.side_effect = _s3_error("InternalError")
        with pytest.raises(HTTPException) as exc_info:
            storage.get("k")
        assert exc_info.value.status_code == 503

    def test_get_connectivity_failure_returns_503_not_500(self, storage: MinioStorage):
        storage._client.get_object.side_effect = ConnectionError("connection refused")
        with pytest.raises(HTTPException) as exc_info:
            storage.get("k")
        assert exc_info.value.status_code == 503


class TestExists:
    def test_exists_true(self, storage: MinioStorage):
        storage._client.stat_object.return_value = MagicMock()
        assert storage.exists("k") is True

    def test_exists_false_on_s3_error(self, storage: MinioStorage):
        storage._client.stat_object.side_effect = _s3_error("NoSuchKey")
        assert storage.exists("k") is False

    def test_exists_malformed_key_returns_503_not_500(self, storage: MinioStorage):
        """Regression: the minio SDK raises plain ValueError client-side for a
        "." or ".." object-name segment — must not leak as an unhandled 500.
        """
        storage._client.stat_object.side_effect = ValueError(
            "object name with '.' or '..' path segment is not supported"
        )
        with pytest.raises(HTTPException) as exc_info:
            storage.exists("k")
        assert exc_info.value.status_code == 503
