import os
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings
from pydantic import BaseModel

COLLECTION_NAME = "docs"
REPO_ROOT = Path(__file__).resolve().parents[3]


class ChunkMetadata(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    uploaded_at: str
    page: int | None = None
    heading: str | None = None


class StoredChunk(BaseModel):
    id: str
    text: str
    embedding: list[float]
    metadata: ChunkMetadata


class ChunkRecord(BaseModel):
    id: str
    text: str
    metadata: ChunkMetadata


class DocumentInfo(BaseModel):
    id: str
    filename: str
    chunk_count: int
    uploaded_at: datetime


def chroma_path() -> Path:
    override = os.environ.get("CHROMA_PATH")
    return Path(override) if override else REPO_ROOT / "data" / "chroma"


@lru_cache(maxsize=1)
def get_collection() -> Collection:
    path = chroma_path()
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(path), settings=Settings(anonymized_telemetry=False)
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=None,
    )


_revision = 0


def revision() -> int:
    """Bumped whenever chunks are added or deleted, so caches built from them can expire."""
    return _revision


def _bump_revision() -> None:
    global _revision
    _revision += 1


def add_chunks(chunks: list[StoredChunk]) -> None:
    if not chunks:
        return
    _bump_revision()
    get_collection().add(
        ids=[c.id for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=[c.embedding for c in chunks],
        metadatas=[c.metadata.model_dump(exclude_none=True) for c in chunks],
    )


def count_chunks() -> int:
    return get_collection().count()


def delete_document(document_id: str) -> int:
    collection = get_collection()
    ids = collection.get(where={"document_id": document_id}, include=[])["ids"]
    if ids:
        collection.delete(ids=ids)
        _bump_revision()
    return len(ids)


def all_chunks() -> list[ChunkRecord]:
    result = get_collection().get(include=["documents", "metadatas"])
    return [
        to_record(id_, text, meta)
        for id_, text, meta in zip(
            result["ids"], result["documents"] or [], result["metadatas"] or [], strict=True
        )
    ]


def to_record(chunk_id: str, text: str, metadata: Mapping[str, Any]) -> ChunkRecord:
    return ChunkRecord(id=chunk_id, text=text, metadata=ChunkMetadata(**metadata))


def get_embeddings(ids: list[str]) -> dict[str, list[float]]:
    if not ids:
        return {}
    result = get_collection().get(ids=ids, include=["embeddings"])
    return {id_: [float(x) for x in vec] for id_, vec in zip(result["ids"], result["embeddings"])}


def list_documents() -> list[DocumentInfo]:
    metadatas = get_collection().get(include=["metadatas"])["metadatas"] or []
    documents = _group_by_document(metadatas)
    return sorted(documents, key=lambda d: d.uploaded_at, reverse=True)


def _group_by_document(metadatas: list[Mapping[str, Any]]) -> list[DocumentInfo]:
    grouped: dict[str, DocumentInfo] = {}
    for meta in metadatas:
        doc_id = str(meta["document_id"])
        if doc_id in grouped:
            grouped[doc_id].chunk_count += 1
            continue
        grouped[doc_id] = DocumentInfo(
            id=doc_id,
            filename=str(meta["filename"]),
            chunk_count=1,
            uploaded_at=datetime.fromisoformat(str(meta["uploaded_at"])),
        )
    return list(grouped.values())
