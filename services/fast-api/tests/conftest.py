"""Shared fixtures: sample files, TestClient, and a MinIO-reachability skip."""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw


@pytest.fixture()
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


@pytest.fixture(scope="session")
def minio_reachable() -> bool:
    """Real MinIO connectivity check — router-level tests that hit real MinIO
    skip cleanly instead of failing when Docker isn't running.
    """
    from app.config import get_settings
    from app.services.minio_storage import MinioStorage

    try:
        MinioStorage(get_settings())
        return True
    except Exception:
        return False


@pytest.fixture()
def require_minio(minio_reachable: bool) -> None:
    if not minio_reachable:
        pytest.skip("MinIO is not reachable (docker compose up -d minio minio-init)")


def _minimal_pdf_bytes() -> bytes:
    """A syntactically valid but minimal/empty PDF (no real text layer)."""
    return b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _text_image_bytes(text: str = "Hello OCR World 12345") -> bytes:
    image = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 30), text, fill="black")
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _embedded_text_pdf_bytes(text: str = "Invoice total due is one hundred dollars") -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text)
    data = doc.tobytes()
    doc.close()
    return data


def _scanned_only_pdf_bytes() -> bytes:
    """A PDF with an embedded image and no text layer — forces the OCR fallback."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, 450, 150)
    page.insert_image(rect, stream=_text_image_bytes())
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture()
def minimal_pdf_bytes() -> bytes:
    return _minimal_pdf_bytes()


@pytest.fixture()
def text_image_bytes() -> bytes:
    return _text_image_bytes()


@pytest.fixture()
def embedded_text_pdf_bytes() -> bytes:
    return _embedded_text_pdf_bytes()


@pytest.fixture()
def scanned_only_pdf_bytes() -> bytes:
    return _scanned_only_pdf_bytes()
