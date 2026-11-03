import os
import re
from collections.abc import Sequence
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

import numpy as np
from pydantic import BaseModel
from rank_bm25 import BM25Okapi

from app import ingest, store

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

RERANKER_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RRF_K = 60
# Chosen from `uv run python -m eval.run`: hybrid matched hybrid+rerank on quality
# at a fraction of the latency; see CLAUDE.md for the numbers.
DEFAULT_MODE = "hybrid"
DEFAULT_RERANK = False
DEFAULT_CANDIDATES = 20
TOKEN_RE = re.compile(r"\w+")


class Chunk(BaseModel):
    document_id: str
    text: str
    filename: str
    page: int | None = None
    heading: str | None = None
    chunk_index: int
    # Cosine similarity between the question and this chunk (same scale in every mode).
    score: float


class RetrievalSettings(BaseModel):
    mode: Literal["vector", "hybrid"] = DEFAULT_MODE
    rerank: bool = DEFAULT_RERANK
    candidates: int = DEFAULT_CANDIDATES

    @classmethod
    def from_env(cls) -> "RetrievalSettings":
        """Reads RETRIEVAL_MODE, RERANK and RETRIEVAL_CANDIDATES from the environment."""
        mode = os.environ.get("RETRIEVAL_MODE", DEFAULT_MODE).strip().lower()
        if mode not in ("vector", "hybrid"):
            raise ValueError(f"RETRIEVAL_MODE must be 'vector' or 'hybrid', got {mode!r}.")
        return cls(
            mode=mode,  # type: ignore[arg-type]
            rerank=_env_bool("RERANK", DEFAULT_RERANK),
            candidates=_env_positive_int("RETRIEVAL_CANDIDATES", DEFAULT_CANDIDATES),
        )


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    if not raw.strip().isdigit() or int(raw) < 1:
        raise ValueError(f"{name} must be a positive whole number, got {raw!r}.")
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    if raw.strip().lower() in ("1", "true", "yes", "on"):
        return True
    if raw.strip().lower() in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name} must be true or false, got {raw!r}.")


def retrieve(
    question: str,
    k: int = 5,
    document_ids: Sequence[str] | None = None,
    settings: RetrievalSettings | None = None,
) -> list[Chunk]:
    """Return the k best chunks for the question, best first.

    Pipeline: vector search (plus BM25 merged by reciprocal rank fusion in
    hybrid mode), optionally reranked by a cross-encoder. Restricted to
    `document_ids` when given and non-empty.
    """
    settings = settings or RetrievalSettings.from_env()
    pool = max(k, settings.candidates)
    embedding = ingest.embed([question])[0]
    ranked = _vector_ranking(embedding, pool, document_ids)
    if settings.mode == "hybrid":
        ranked = _fuse(ranked, _bm25_ranking(question, pool, document_ids))[:pool]
    if settings.rerank:
        ranked = _rerank(question, ranked[: settings.candidates])
    return _to_chunks(ranked[:k], embedding)


# --- vector -----------------------------------------------------------------


def _document_filter(document_ids: Sequence[str] | None) -> dict[str, Any] | None:
    if not document_ids:
        return None
    return {"document_id": {"$in": list(document_ids)}}


def _vector_ranking(
    embedding: list[float], n: int, document_ids: Sequence[str] | None
) -> list[store.ChunkRecord]:
    result = store.get_collection().query(
        query_embeddings=[embedding],
        n_results=n,
        where=_document_filter(document_ids),
        include=["documents", "metadatas"],
    )
    ids = (result["ids"] or [[]])[0]
    texts = (result["documents"] or [[]])[0]
    metas = (result["metadatas"] or [[]])[0]
    return [store.to_record(i, t, m) for i, t, m in zip(ids, texts, metas, strict=True)]


# --- BM25 -------------------------------------------------------------------


class _Bm25Index(NamedTuple):
    bm25: BM25Okapi | None
    records: list[store.ChunkRecord]


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


@lru_cache(maxsize=2)
def _bm25_index(chroma_path: str, revision: int) -> _Bm25Index:
    """Index of every stored chunk; rebuilt when the store's path or revision changes."""
    records = store.all_chunks()
    if not records:
        return _Bm25Index(None, [])
    return _Bm25Index(BM25Okapi([tokenize(r.text) for r in records]), records)


def _bm25_ranking(
    question: str, n: int, document_ids: Sequence[str] | None
) -> list[store.ChunkRecord]:
    index = _bm25_index(str(store.chroma_path()), store.revision())
    tokens = tokenize(question)
    if index.bm25 is None or not tokens:
        return []
    scores = index.bm25.get_scores(tokens)
    allowed = set(document_ids) if document_ids else None
    ranked: list[store.ChunkRecord] = []
    for i in np.argsort(-scores):
        if scores[i] <= 0:
            break
        record = index.records[i]
        if allowed is None or record.metadata.document_id in allowed:
            ranked.append(record)
            if len(ranked) == n:
                break
    return ranked


# --- fusion and reranking ---------------------------------------------------


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    """Merge ranked id lists: each id scores the sum of 1 / (k + rank) over the lists."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda item: scores[item], reverse=True)


def _fuse(
    vector: list[store.ChunkRecord], bm25: list[store.ChunkRecord]
) -> list[store.ChunkRecord]:
    by_id = {r.id: r for r in [*bm25, *vector]}
    merged = reciprocal_rank_fusion([[r.id for r in vector], [r.id for r in bm25]])
    return [by_id[i] for i in merged]


@lru_cache(maxsize=1)
def get_reranker() -> "CrossEncoder":
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANKER_NAME)


def _rerank(question: str, records: list[store.ChunkRecord]) -> list[store.ChunkRecord]:
    if not records:
        return []
    scores = get_reranker().predict([(question, r.text) for r in records])
    return [records[i] for i in np.argsort(-np.asarray(scores))]


def warm_up(settings: RetrievalSettings) -> None:
    """Load the models a request would otherwise load lazily."""
    if settings.rerank:
        get_reranker()


# --- output -----------------------------------------------------------------


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b)) / denominator if denominator else 0.0


def _to_chunks(records: list[store.ChunkRecord], embedding: list[float]) -> list[Chunk]:
    vectors = store.get_embeddings([r.id for r in records])
    query = np.asarray(embedding)
    return [
        Chunk(
            document_id=r.metadata.document_id,
            text=r.text,
            filename=r.metadata.filename,
            page=r.metadata.page,
            heading=r.metadata.heading,
            chunk_index=r.metadata.chunk_index,
            score=_cosine(query, np.asarray(vectors[r.id])),
        )
        for r in records
    ]
