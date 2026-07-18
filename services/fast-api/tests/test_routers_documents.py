"""HTTP-level tests for /documents/upload and /documents/{id}/extract.

These exercise the real MinIO + Tesseract stack (skipped automatically if
MinIO isn't reachable — see conftest.require_minio) since they're verifying
the full request/response contract, not just internal logic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("require_minio")


class TestUpload:
    def test_valid_pdf_upload_succeeds(self, client: TestClient, embedded_text_pdf_bytes: bytes):
        response = client.post(
            "/documents/upload",
            files={"file": ("invoice.pdf", embedded_text_pdf_bytes, "application/pdf")},
            data={"tenant_id": "test-tenant"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == "test-tenant"
        assert body["filename"] == "invoice.pdf"
        assert body["storage"] == "minio"
        assert body["object_key"] == f"test-tenant/{body['document_id']}/invoice.pdf"

    def test_rejected_file_type_returns_415(self, client: TestClient):
        response = client.post(
            "/documents/upload",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 415

    def test_empty_file_returns_400(self, client: TestClient):
        response = client.post(
            "/documents/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400

    def test_tenant_id_path_traversal_returns_400(
        self, client: TestClient, embedded_text_pdf_bytes: bytes
    ):
        response = client.post(
            "/documents/upload",
            files={"file": ("invoice.pdf", embedded_text_pdf_bytes, "application/pdf")},
            data={"tenant_id": "../evil"},
        )
        assert response.status_code == 400


class TestExtract:
    def test_extract_round_trip(self, client: TestClient, embedded_text_pdf_bytes: bytes):
        upload = client.post(
            "/documents/upload",
            files={"file": ("invoice.pdf", embedded_text_pdf_bytes, "application/pdf")},
            data={"tenant_id": "test-tenant"},
        )
        doc_id = upload.json()["document_id"]

        response = client.post(f"/documents/{doc_id}/extract?tenant_id=test-tenant")
        assert response.status_code == 200
        body = response.json()
        assert body["engine"] == "pdf-text"
        assert "Invoice total due" in body["text"]

    def test_wrong_tenant_returns_404(self, client: TestClient, embedded_text_pdf_bytes: bytes):
        """Regression test at the HTTP layer for the tenant-isolation bug."""
        upload = client.post(
            "/documents/upload",
            files={"file": ("invoice.pdf", embedded_text_pdf_bytes, "application/pdf")},
            data={"tenant_id": "acme"},
        )
        doc_id = upload.json()["document_id"]

        response = client.post(f"/documents/{doc_id}/extract?tenant_id=mallory")
        assert response.status_code == 404

    def test_nonexistent_document_returns_404(self, client: TestClient):
        response = client.post(
            "/documents/00000000-0000-0000-0000-000000000000/extract?tenant_id=test-tenant"
        )
        assert response.status_code == 404
