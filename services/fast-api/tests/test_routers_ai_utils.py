"""HTTP-level tests for /ai/summarize, /ai/classify, /ai/chunk.

Covers both the direct-text path (no external deps) and the document_id path
(real MinIO + Tesseract, skipped if unreachable — see conftest.require_minio).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestDirectText:
    """No document_id involved — these never need MinIO/Tesseract."""

    def test_summarize_with_direct_text(self, client: TestClient):
        response = client.post(
            "/ai/summarize",
            json={"text": "First sentence here. Second sentence here. Third one too."},
        )
        assert response.status_code == 200
        assert response.json()["document_id"] is None

    def test_classify_with_direct_text(self, client: TestClient):
        response = client.post(
            "/ai/classify",
            json={"text": "Invoice total due, subtotal, tax, and payment terms."},
        )
        assert response.status_code == 200
        assert response.json()["label"] == "invoice"

    def test_chunk_with_direct_text(self, client: TestClient):
        response = client.post(
            "/ai/chunk",
            json={"text": "abcdefghijklmnopqrstuvwxyz", "chunk_size": 10, "chunk_overlap": 3},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["chunk_count"] == 4

    def test_chunk_invalid_overlap_returns_400(self, client: TestClient):
        response = client.post(
            "/ai/chunk",
            json={"text": "some text", "chunk_size": 10, "chunk_overlap": 10},
        )
        assert response.status_code == 400

    def test_missing_text_and_document_id_returns_400(self, client: TestClient):
        response = client.post("/ai/summarize", json={})
        assert response.status_code == 400 or response.status_code == 422


@pytest.mark.usefixtures("require_minio")
class TestDocumentIdPath:
    def test_summarize_via_document_id(self, client: TestClient, embedded_text_pdf_bytes: bytes):
        upload = client.post(
            "/documents/upload",
            files={"file": ("invoice.pdf", embedded_text_pdf_bytes, "application/pdf")},
            data={"tenant_id": "test-tenant"},
        )
        doc_id = upload.json()["document_id"]

        response = client.post(
            "/ai/summarize",
            json={"document_id": doc_id, "tenant_id": "test-tenant"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["document_id"] == doc_id
        assert "Invoice total due" in body["summary"]

    def test_wrong_tenant_returns_404(self, client: TestClient, embedded_text_pdf_bytes: bytes):
        """Regression test: the Step 5 tenant-isolation fix must carry through
        the shared load_and_extract() path used by the AI-utils endpoints too.
        """
        upload = client.post(
            "/documents/upload",
            files={"file": ("invoice.pdf", embedded_text_pdf_bytes, "application/pdf")},
            data={"tenant_id": "acme"},
        )
        doc_id = upload.json()["document_id"]

        response = client.post(
            "/ai/summarize",
            json={"document_id": doc_id, "tenant_id": "mallory"},
        )
        assert response.status_code == 404

    def test_document_id_path_traversal_returns_400(
        self, client: TestClient, embedded_text_pdf_bytes: bytes
    ):
        """Regression test for the Step 6 bug: document_id arrives as a JSON
        body field here (unlike /documents/{id}/extract's path parameter), so
        nothing but explicit sanitization stops a "../" value from reaching
        MinIO's key construction.
        """
        upload = client.post(
            "/documents/upload",
            files={"file": ("invoice.pdf", embedded_text_pdf_bytes, "application/pdf")},
            data={"tenant_id": "acme"},
        )
        doc_id = upload.json()["document_id"]

        response = client.post(
            "/ai/summarize",
            json={"document_id": f"../acme/{doc_id}", "tenant_id": "mallory"},
        )
        assert response.status_code == 400

    def test_classify_and_chunk_also_work_via_document_id(
        self, client: TestClient, embedded_text_pdf_bytes: bytes
    ):
        upload = client.post(
            "/documents/upload",
            files={"file": ("invoice.pdf", embedded_text_pdf_bytes, "application/pdf")},
            data={"tenant_id": "test-tenant"},
        )
        doc_id = upload.json()["document_id"]

        classify_response = client.post(
            "/ai/classify", json={"document_id": doc_id, "tenant_id": "test-tenant"}
        )
        assert classify_response.status_code == 200
        assert classify_response.json()["label"] == "invoice"

        chunk_response = client.post(
            "/ai/chunk", json={"document_id": doc_id, "tenant_id": "test-tenant"}
        )
        assert chunk_response.status_code == 200
        assert chunk_response.json()["chunk_count"] >= 1
