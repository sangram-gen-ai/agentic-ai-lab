"""Tests for DocumentStore — uses an in-memory fake storage (no real MinIO
needed) so these run fast and always, everywhere.

The tenant-isolation tests are regression tests for a real bug: resolve()
used to trust an in-memory cache hit by document_id alone, without checking
that the requested tenant_id matched the cached document's actual tenant —
so once a document had been resolved once, ANY tenant_id could read it.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.document_store import DocumentStore


class FakeMinioStorage:
    """In-memory stand-in for MinioStorage's public interface."""

    def __init__(self):
        self._objects: dict[str, bytes] = {}
        self.bucket = "test-bucket"

    def put(self, *, object_key: str, content: bytes, content_type: str) -> None:
        self._objects[object_key] = content

    def get(self, object_key: str) -> bytes:
        if object_key not in self._objects:
            raise HTTPException(status_code=404, detail=f"Object not found: {object_key}")
        return self._objects[object_key]

    def exists(self, object_key: str) -> bool:
        return object_key in self._objects


@pytest.fixture()
def store() -> DocumentStore:
    return DocumentStore(storage=FakeMinioStorage())


class TestSave:
    def test_save_writes_object_and_sidecar_and_caches(self, store: DocumentStore):
        doc = store.save(
            tenant_id="acme",
            filename="invoice.pdf",
            content_type="application/pdf",
            content=b"pdf bytes",
        )
        assert doc.tenant_id == "acme"
        assert doc.object_key == f"acme/{doc.document_id}/invoice.pdf"
        assert store.get(doc.document_id) is doc  # cached in-process

        # The sidecar was actually written to storage, not just the file.
        meta_key = f"acme/{doc.document_id}/.meta.json"
        assert store.storage.exists(meta_key)


class TestResolveTenantIsolation:
    """The critical regression coverage."""

    def test_correct_tenant_resolves_from_cache(self, store: DocumentStore):
        doc = store.save(
            tenant_id="acme", filename="f.pdf", content_type="application/pdf", content=b"x"
        )
        resolved = store.resolve(doc.document_id, "acme")
        assert resolved.document_id == doc.document_id

    def test_wrong_tenant_404s_even_though_cached(self, store: DocumentStore):
        """Upload as 'acme', then immediately request as 'mallory' — this is
        exactly the scenario that used to leak data.
        """
        doc = store.save(
            tenant_id="acme", filename="f.pdf", content_type="application/pdf", content=b"secret"
        )
        with pytest.raises(HTTPException) as exc_info:
            store.resolve(doc.document_id, "mallory")
        assert exc_info.value.status_code == 404

    def test_wrong_tenant_404s_after_a_successful_resolve_warmed_the_cache(
        self, store: DocumentStore
    ):
        """Belt-and-suspenders: even after a legitimate resolve() call for the
        correct tenant has populated/touched the cache, a different tenant_id
        must still be rejected on a subsequent call.
        """
        doc = store.save(
            tenant_id="acme", filename="f.pdf", content_type="application/pdf", content=b"secret"
        )
        store.resolve(doc.document_id, "acme")  # warm the cache

        with pytest.raises(HTTPException) as exc_info:
            store.resolve(doc.document_id, "mallory")
        assert exc_info.value.status_code == 404

    def test_nonexistent_document_404s(self, store: DocumentStore):
        with pytest.raises(HTTPException) as exc_info:
            store.resolve("00000000-0000-0000-0000-000000000000", "acme")
        assert exc_info.value.status_code == 404


class TestResolveColdPath:
    """Simulates a process restart: a fresh DocumentStore backed by the SAME
    storage, with an empty in-memory cache, must still resolve via the
    .meta.json sidecar — and must still enforce tenant isolation there too.
    """

    def test_cold_resolve_reloads_from_sidecar(self):
        storage = FakeMinioStorage()
        original_store = DocumentStore(storage=storage)
        doc = original_store.save(
            tenant_id="acme", filename="f.pdf", content_type="application/pdf", content=b"x"
        )

        fresh_store = DocumentStore(storage=storage)  # empty cache, same backing storage
        resolved = fresh_store.resolve(doc.document_id, "acme")
        assert resolved.document_id == doc.document_id
        assert resolved.filename == "f.pdf"

    def test_cold_resolve_wrong_tenant_404s(self):
        storage = FakeMinioStorage()
        original_store = DocumentStore(storage=storage)
        doc = original_store.save(
            tenant_id="acme", filename="f.pdf", content_type="application/pdf", content=b"x"
        )

        fresh_store = DocumentStore(storage=storage)
        with pytest.raises(HTTPException) as exc_info:
            fresh_store.resolve(doc.document_id, "mallory")
        assert exc_info.value.status_code == 404

    def test_corrupt_sidecar_metadata_returns_500(self):
        storage = FakeMinioStorage()
        storage._objects["acme/doc-1/.meta.json"] = b"not valid json"
        store = DocumentStore(storage=storage)

        with pytest.raises(HTTPException) as exc_info:
            store.resolve("doc-1", "acme")
        assert exc_info.value.status_code == 500


class TestResolveAndLoad:
    def test_returns_both_metadata_and_bytes(self, store: DocumentStore):
        doc = store.save(
            tenant_id="acme",
            filename="f.pdf",
            content_type="application/pdf",
            content=b"the actual bytes",
        )
        resolved_doc, content = store.resolve_and_load(doc.document_id, "acme")
        assert resolved_doc.document_id == doc.document_id
        assert content == b"the actual bytes"

    def test_wrong_tenant_404s(self, store: DocumentStore):
        doc = store.save(
            tenant_id="acme", filename="f.pdf", content_type="application/pdf", content=b"x"
        )
        with pytest.raises(HTTPException) as exc_info:
            store.resolve_and_load(doc.document_id, "mallory")
        assert exc_info.value.status_code == 404
