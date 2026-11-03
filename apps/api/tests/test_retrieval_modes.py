from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import ingest, retrieve, store
from app.retrieve import RetrievalSettings, reciprocal_rank_fusion, retrieve as run_retrieve


def ingest_fixtures(sample_md: bytes, baking_md: bytes) -> tuple[str, str]:
    solar = ingest.ingest_document("sample.md", sample_md).document_id
    baking = ingest.ingest_document("baking.md", baking_md).document_id
    return solar, baking


def stub_vector_order(monkeypatch: pytest.MonkeyPatch, texts_in_order: list[str]) -> None:
    """Make vector search return the stored chunks whose text starts with these strings, in order."""
    by_start = {r.text[:12]: r for r in store.all_chunks()}
    ordered = [by_start[t[:12]] for t in texts_in_order]
    monkeypatch.setattr(retrieve, "_vector_ranking", lambda *_args: ordered)


# --- reciprocal rank fusion --------------------------------------------------


def test_rrf_rewards_items_that_appear_in_both_rankings() -> None:
    # d: 1/64 + 1/61 beats a: 1/61; b and e tie at 1/62 (b first, as it was seen first); c: 1/63.
    assert reciprocal_rank_fusion([["a", "b", "c", "d"], ["d", "e"]]) == ["d", "a", "b", "e", "c"]


def test_rrf_scores_follow_the_formula() -> None:
    # "x" is 1st in both lists: 2/(60+1); "y" is 2nd in one list only: 1/(60+2).
    assert reciprocal_rank_fusion([["x", "y"], ["x"]]) == ["x", "y"]
    assert reciprocal_rank_fusion([["y", "x"], ["x"]], k=1) == ["x", "y"]


def test_rrf_handles_empty_input() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


# --- settings ---------------------------------------------------------------


def test_settings_read_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_MODE", "Hybrid")
    monkeypatch.setenv("RERANK", "true")
    monkeypatch.setenv("RETRIEVAL_CANDIDATES", "30")
    assert RetrievalSettings.from_env() == RetrievalSettings(mode="hybrid", rerank=True, candidates=30)


def test_settings_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL_MODE", "RERANK", "RETRIEVAL_CANDIDATES"):
        monkeypatch.delenv(name, raising=False)
    settings = RetrievalSettings.from_env()
    assert settings.mode == retrieve.DEFAULT_MODE
    assert settings.rerank is retrieve.DEFAULT_RERANK
    assert settings.candidates == 20


def test_settings_reject_bad_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_MODE", "semantic")
    with pytest.raises(ValueError, match="RETRIEVAL_MODE"):
        RetrievalSettings.from_env()
    monkeypatch.setenv("RETRIEVAL_MODE", "vector")
    monkeypatch.setenv("RERANK", "maybe")
    with pytest.raises(ValueError, match="RERANK"):
        RetrievalSettings.from_env()


# --- BM25 -------------------------------------------------------------------


def test_bm25_ranking_matches_keywords_and_respects_the_document_filter(
    client: TestClient, sample_md: bytes, baking_md: bytes
) -> None:
    solar, baking = ingest_fixtures(sample_md, baking_md)

    hits = retrieve._bm25_ranking("flour oven yeast", 5, None)
    assert hits and {h.metadata.filename for h in hits} == {"baking.md"}

    assert retrieve._bm25_ranking("flour oven", 5, [solar]) == []
    only_baking = retrieve._bm25_ranking("flour oven", 5, [baking])
    assert only_baking and {h.metadata.document_id for h in only_baking} == {baking}
    assert retrieve._bm25_ranking("zzzunknownword", 5, None) == []
    assert retrieve._bm25_ranking("   ", 5, None) == []


def test_bm25_index_is_rebuilt_after_documents_change(
    client: TestClient, sample_md: bytes, baking_md: bytes
) -> None:
    _, baking = ingest_fixtures(sample_md, baking_md)
    assert retrieve._bm25_ranking("flour", 5, None)

    store.delete_document(baking)

    assert retrieve._bm25_ranking("flour", 5, None) == []


def test_bm25_on_an_empty_store_returns_nothing(client: TestClient) -> None:
    assert retrieve._bm25_ranking("anything", 5, None) == []


# --- hybrid -----------------------------------------------------------------


def test_hybrid_surfaces_a_chunk_that_only_keyword_search_ranks_high(
    client: TestClient, sample_md: bytes, baking_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingest_fixtures(sample_md, baking_md)
    # Vector search ranks the solar chunks first and the Sourdough chunk last...
    stub_vector_order(
        monkeypatch,
        ["# Solar Syste", "## Inner Pla", "## Outer Pla", "## Sourdough", "# Baking Bre"],
    )
    vector_top = run_retrieve("sourdough starter", k=3, settings=RetrievalSettings(mode="vector"))
    assert "Sourdough" not in {c.heading for c in vector_top}

    # ...but BM25 puts it first, so fusion pulls it into the top 3.
    hybrid_top = run_retrieve("sourdough starter", k=3, settings=RetrievalSettings(mode="hybrid"))
    assert "Sourdough" in {c.heading for c in hybrid_top}


def test_hybrid_respects_document_filter(
    client: TestClient, sample_md: bytes, baking_md: bytes
) -> None:
    solar, _ = ingest_fixtures(sample_md, baking_md)
    chunks = run_retrieve("flour bread planets", k=10, document_ids=[solar],
                          settings=RetrievalSettings(mode="hybrid"))
    assert chunks and {c.filename for c in chunks} == {"sample.md"}


def test_scores_are_cosine_similarity_in_every_mode(
    client: TestClient, sample_md: bytes, baking_md: bytes
) -> None:
    ingest_fixtures(sample_md, baking_md)
    for mode in ("vector", "hybrid"):
        chunks = run_retrieve("gas giants planets", k=4, settings=RetrievalSettings(mode=mode))
        assert all(-1.0 <= c.score <= 1.0 for c in chunks)
    top = run_retrieve("gas giants planets", k=1, settings=RetrievalSettings(mode="vector"))[0]
    assert top.score > 0.5


# --- reranking --------------------------------------------------------------


class FakeReranker:
    """Scores a (question, text) pair by how many times 'bread' appears in the text."""

    def __init__(self) -> None:
        self.seen: list[list[tuple[str, str]]] = []

    def predict(self, pairs: list[tuple[str, str]]) -> np.ndarray:
        self.seen.append(pairs)
        return np.array([float(text.lower().count("bread")) for _, text in pairs])


def test_rerank_reorders_the_candidates_and_cuts_to_k(
    client: TestClient, sample_md: bytes, baking_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingest_fixtures(sample_md, baking_md)
    reranker = FakeReranker()
    monkeypatch.setattr(retrieve, "get_reranker", lambda: reranker)
    # Vector search would put the baking chunks last of 5.
    stub_vector_order(
        monkeypatch,
        ["# Solar Syste", "## Inner Pla", "## Outer Pla", "## Sourdough", "# Baking Bre"],
    )

    without = run_retrieve("anything", k=2, settings=RetrievalSettings(mode="vector"))
    with_rerank = run_retrieve(
        "anything", k=2, settings=RetrievalSettings(mode="vector", rerank=True, candidates=5)
    )

    assert {c.filename for c in without} == {"sample.md"}
    assert with_rerank[0].filename == "baking.md"
    assert len(with_rerank) == 2
    assert len(reranker.seen[0]) == 5  # all candidates were scored, then cut to k


def test_rerank_only_scores_the_requested_number_of_candidates(
    client: TestClient, sample_md: bytes, baking_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingest_fixtures(sample_md, baking_md)
    reranker = FakeReranker()
    monkeypatch.setattr(retrieve, "get_reranker", lambda: reranker)

    run_retrieve("bread", k=2, settings=RetrievalSettings(rerank=True, candidates=3))

    assert len(reranker.seen[0]) == 3


def test_rerank_is_skipped_when_disabled(
    client: TestClient, sample_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingest.ingest_document("sample.md", sample_md)

    def explode() -> None:
        raise AssertionError("reranker should not load")

    monkeypatch.setattr(retrieve, "get_reranker", explode)
    assert run_retrieve("planets", k=2, settings=RetrievalSettings(rerank=False))


def test_warm_up_loads_the_reranker_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = SimpleNamespace(count=0)

    def fake_loader() -> None:
        loaded.count += 1

    monkeypatch.setattr(retrieve, "get_reranker", fake_loader)
    retrieve.warm_up(RetrievalSettings(rerank=False))
    assert loaded.count == 0
    retrieve.warm_up(RetrievalSettings(rerank=True))
    assert loaded.count == 1
