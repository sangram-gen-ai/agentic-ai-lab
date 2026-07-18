"""Tests for OcrService — uses the real Tesseract/PyMuPDF installed locally
(no mocking of the OCR engine itself; only the "missing binary" path is
simulated by pointing tesseract_cmd at a nonexistent binary).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.services.ocr import OcrService


@pytest.fixture()
def svc() -> OcrService:
    return OcrService(Settings())


class TestExtractImage:
    def test_image_ocr_extracts_text(self, svc: OcrService, text_image_bytes: bytes):
        result = svc.extract(text_image_bytes, "image/png")
        assert result.engine == "tesseract"
        assert result.page_count == 1
        assert "OCR" in result.text or "ocr" in result.text.lower()

    def test_corrupt_image_bytes_returns_422(self, svc: OcrService):
        with pytest.raises(HTTPException) as exc_info:
            svc.extract(b"not a real image at all", "image/png")
        assert exc_info.value.status_code == 422


class TestExtractPdf:
    def test_embedded_text_pdf_uses_pdf_text_engine(
        self, svc: OcrService, embedded_text_pdf_bytes: bytes
    ):
        result = svc.extract(embedded_text_pdf_bytes, "application/pdf")
        assert result.engine == "pdf-text"
        assert "Invoice total due" in result.text
        assert result.pages[0].method == "pdf-text"

    def test_scanned_pdf_falls_back_to_tesseract(
        self, svc: OcrService, scanned_only_pdf_bytes: bytes
    ):
        result = svc.extract(scanned_only_pdf_bytes, "application/pdf")
        assert result.engine == "tesseract"
        assert result.pages[0].method == "tesseract"
        assert len(result.text.strip()) > 0

    def test_corrupt_pdf_bytes_returns_422(self, svc: OcrService):
        with pytest.raises(HTTPException) as exc_info:
            svc.extract(b"not a real pdf at all", "application/pdf")
        assert exc_info.value.status_code == 422


class TestUnsupportedType:
    def test_unsupported_content_type_returns_415(self, svc: OcrService):
        with pytest.raises(HTTPException) as exc_info:
            svc.extract(b"whatever", "text/plain")
        assert exc_info.value.status_code == 415


class TestTesseractNotFound:
    """Regression tests: a missing Tesseract binary must surface as 503, not
    leak as an uncaught exception (the bug found and fixed in Step 4) and not
    get silently downgraded to 422 by an outer generic exception handler (the
    fix made when _run_tesseract() was extracted during the duplication cleanup).
    """

    @pytest.fixture()
    def broken_svc(self) -> OcrService:
        return OcrService(Settings(tesseract_cmd="/nonexistent/tesseract/binary"))

    def test_image_path_returns_503(self, broken_svc: OcrService, text_image_bytes: bytes):
        with pytest.raises(HTTPException) as exc_info:
            broken_svc.extract(text_image_bytes, "image/png")
        assert exc_info.value.status_code == 503

    def test_scanned_pdf_page_path_returns_503(
        self, broken_svc: OcrService, scanned_only_pdf_bytes: bytes
    ):
        with pytest.raises(HTTPException) as exc_info:
            broken_svc.extract(scanned_only_pdf_bytes, "application/pdf")
        assert exc_info.value.status_code == 503
