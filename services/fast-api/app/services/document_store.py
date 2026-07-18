"""Document metadata registry + MinIO persistence.

Bytes live in MinIO under ``{tenant_id}/{document_id}/{filename}``.
A ``.meta.json`` sidecar is written alongside so extract works after restarts
(when the in-process registry is empty).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException, status

from app.services.minio_storage import (
    MinioStorage,
    build_meta_key,
    build_object_key,
    get_minio_storage,
)


@dataclass
class StoredDocument:
    document_id: str
    tenant_id: str
    filename: str
    content_type: str
    size_bytes: int
    object_key: str
    bucket: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_meta_dict(self) -> dict:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data

    @classmethod
    def from_meta_dict(cls, data: dict) -> StoredDocument:
        created = data.get("created_at")
        if isinstance(created, str):
            created_at = datetime.fromisoformat(created)
        else:
            created_at = datetime.now(timezone.utc)
        return cls(
            document_id=data["document_id"],
            tenant_id=data["tenant_id"],
            filename=data["filename"],
            content_type=data["content_type"],
            size_bytes=int(data["size_bytes"]),
            object_key=data["object_key"],
            bucket=data["bucket"],
            created_at=created_at,
        )


class DocumentStore:
    """Put bytes + metadata in MinIO; cache metadata in memory for fast lookup."""

    def __init__(self, storage: MinioStorage | None = None) -> None:
        self._storage = storage
        self._docs: dict[str, StoredDocument] = {}
        self._lock = Lock()

    @property
    def storage(self) -> MinioStorage:
        if self._storage is None:
            self._storage = get_minio_storage()
        return self._storage

    def save(
        self,
        *,
        tenant_id: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> StoredDocument:
        document_id = str(uuid4())
        object_key = build_object_key(tenant_id, document_id, filename)

        self.storage.put(
            object_key=object_key,
            content=content,
            content_type=content_type,
        )

        doc = StoredDocument(
            document_id=document_id,
            tenant_id=tenant_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            object_key=object_key,
            bucket=self.storage.bucket,
        )

        meta_key = build_meta_key(tenant_id, document_id)
        meta_bytes = json.dumps(doc.to_meta_dict(), indent=2).encode("utf-8")
        self.storage.put(
            object_key=meta_key,
            content=meta_bytes,
            content_type="application/json",
        )

        with self._lock:
            self._docs[document_id] = doc
        return doc

    def get(self, document_id: str) -> StoredDocument | None:
        with self._lock:
            return self._docs.get(document_id)

    def resolve(self, document_id: str, tenant_id: str) -> StoredDocument:
        """Find document metadata in memory, or reload from MinIO sidecar.

        Always re-validates tenant_id, even against the in-memory cache — a
        cache hit for the right document_id under the wrong tenant must still
        404. Without this check, tenant_id only matters on the very first
        resolve after a restart; every later call would trust the cache and
        skip the check entirely, since save() populates it unconditionally.
        """
        cached = self.get(document_id)
        if cached is not None and cached.tenant_id == tenant_id:
            return cached

        meta_key = build_meta_key(tenant_id, document_id)
        if not self.storage.exists(meta_key):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Document '{document_id}' not found for tenant '{tenant_id}'. "
                    "Upload first, or pass the correct tenant_id query param."
                ),
            )

        raw = self.storage.get(meta_key)
        try:
            doc = StoredDocument.from_meta_dict(json.loads(raw.decode("utf-8")))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Corrupt metadata for document '{document_id}'.",
            ) from exc

        with self._lock:
            self._docs[document_id] = doc
        return doc

    def resolve_and_load(self, document_id: str, tenant_id: str) -> tuple[StoredDocument, bytes]:
        """Resolve document metadata, then load its bytes from MinIO.

        Shared by every caller that needs both the document + its content
        (the /extract endpoint and the AI-utils text_source helper), so this
        two-step sequence isn't reimplemented inline at each call site.
        """
        doc = self.resolve(document_id, tenant_id)
        content = self.storage.get(doc.object_key)
        return doc, content


document_store = DocumentStore()
