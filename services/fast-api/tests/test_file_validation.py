"""Unit tests for extension/content-type/magic-byte validation and path-segment
sanitization — pure logic, no external services needed.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.file_validation import (
    sanitize_path_segment,
    sanitize_tenant_id,
    validate_upload,
)


class _FakeUploadFile:
    """Minimal stand-in exposing just what validate_upload reads."""

    def __init__(self, filename: str | None, content_type: str | None):
        self.filename = filename
        self.content_type = content_type


class TestSanitizePathSegment:
    def test_accepts_normal_values(self):
        assert sanitize_path_segment("invoice.pdf", field_name="filename") == "invoice.pdf"
        assert sanitize_path_segment("invoice (draft).pdf", field_name="filename") == (
            "invoice (draft).pdf"
        )
        assert sanitize_path_segment("some-uuid-1234", field_name="document_id") == "some-uuid-1234"

    @pytest.mark.parametrize("value", ["", ".", ".."])
    def test_rejects_empty_or_dot_segments(self, value):
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_segment(value, field_name="tenant_id")
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize(
        "value",
        ["../evil", "a/b", "a\\b", "../../etc/passwd.pdf", "tenant/../other"],
    )
    def test_rejects_path_separators(self, value):
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_segment(value, field_name="tenant_id")
        assert exc_info.value.status_code == 400

    def test_rejects_null_byte(self):
        with pytest.raises(HTTPException) as exc_info:
            sanitize_path_segment("a\x00b", field_name="filename")
        assert exc_info.value.status_code == 400


class TestSanitizeTenantId:
    def test_strips_whitespace(self):
        assert sanitize_tenant_id("  demo  ") == "demo"

    def test_defaults_blank_to_default(self):
        assert sanitize_tenant_id("") == "default"
        assert sanitize_tenant_id("   ") == "default"

    def test_rejects_traversal(self):
        with pytest.raises(HTTPException) as exc_info:
            sanitize_tenant_id("../evil")
        assert exc_info.value.status_code == 400


class TestValidateUpload:
    def test_accepts_valid_pdf(self):
        content = b"%PDF-1.1\nsome content"
        file = _FakeUploadFile("sample.pdf", "application/pdf")
        result = validate_upload(file, content, max_bytes=1_000_000)
        assert result.filename == "sample.pdf"
        assert result.content_type == "application/pdf"
        assert result.size_bytes == len(content)

    def test_accepts_valid_png(self):
        content = b"\x89PNG\r\n\x1a\n" + b"rest of png"
        file = _FakeUploadFile("photo.png", "image/png")
        result = validate_upload(file, content, max_bytes=1_000_000)
        assert result.content_type == "image/png"

    def test_rejects_empty_file(self):
        file = _FakeUploadFile("sample.pdf", "application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            validate_upload(file, b"", max_bytes=1_000_000)
        assert exc_info.value.status_code == 400

    def test_rejects_oversized_file(self):
        content = b"%PDF-1.1\n" + b"a" * 100
        file = _FakeUploadFile("sample.pdf", "application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            validate_upload(file, content, max_bytes=10)
        assert exc_info.value.status_code == 413

    def test_rejects_unsupported_extension(self):
        content = b"hello"
        file = _FakeUploadFile("notes.txt", "text/plain")
        with pytest.raises(HTTPException) as exc_info:
            validate_upload(file, content, max_bytes=1_000_000)
        assert exc_info.value.status_code == 415

    def test_rejects_content_type_mismatched_with_extension(self):
        content = b"%PDF-1.1\nreal pdf bytes"
        file = _FakeUploadFile("sample.pdf", "image/png")
        with pytest.raises(HTTPException) as exc_info:
            validate_upload(file, content, max_bytes=1_000_000)
        assert exc_info.value.status_code == 415

    def test_rejects_renamed_file_failing_magic_bytes(self):
        """A .pdf extension whose bytes don't actually start with %PDF."""
        content = b"this is just plain text, not a pdf at all"
        file = _FakeUploadFile("fake.pdf", "application/pdf")
        with pytest.raises(HTTPException) as exc_info:
            validate_upload(file, content, max_bytes=1_000_000)
        assert exc_info.value.status_code == 415
