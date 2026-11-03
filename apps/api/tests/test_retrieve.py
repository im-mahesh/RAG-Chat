from fastapi.testclient import TestClient

from app import ingest
from app.retrieve import retrieve


def test_retrieve_returns_best_matches_first(
    client: TestClient, sample_md: bytes, baking_md: bytes
) -> None:
    ingest.ingest_document("sample.md", sample_md)
    ingest.ingest_document("baking.md", baking_md)

    chunks = retrieve("Which planets are giants?", k=3)

    assert len(chunks) == 3
    assert chunks[0].filename == "sample.md"
    assert [c.score for c in chunks] == sorted((c.score for c in chunks), reverse=True)


def test_retrieve_populates_chunk_fields(client: TestClient, sample_md: bytes) -> None:
    ingest.ingest_document("sample.md", sample_md)

    top = retrieve("gas giants and ice giants planets", k=1)[0]

    assert top.filename == "sample.md"
    assert top.heading == "Outer Planets"
    assert top.page is None
    assert top.chunk_index == 2
    assert "gas giants" in top.text
    assert 0.0 < top.score <= 1.0


def test_retrieve_respects_k(client: TestClient, sample_md: bytes) -> None:
    ingest.ingest_document("sample.md", sample_md)
    assert len(retrieve("planets", k=2)) == 2
    assert len(retrieve("planets", k=50)) == 3


def test_retrieve_filters_by_document_ids(
    client: TestClient, sample_md: bytes, baking_md: bytes
) -> None:
    solar = ingest.ingest_document("sample.md", sample_md).document_id
    baking = ingest.ingest_document("baking.md", baking_md).document_id

    only_baking = retrieve("Which planets are giants?", k=10, document_ids=[baking])
    assert {c.filename for c in only_baking} == {"baking.md"}

    only_solar = retrieve("bread flour oven", k=10, document_ids=[solar])
    assert {c.filename for c in only_solar} == {"sample.md"}

    both = retrieve("bread flour oven", k=10, document_ids=[solar, baking])
    assert {c.filename for c in both} == {"sample.md", "baking.md"}


def test_retrieve_with_unknown_document_id_returns_nothing(
    client: TestClient, sample_md: bytes
) -> None:
    ingest.ingest_document("sample.md", sample_md)
    assert retrieve("planets", document_ids=["does-not-exist"]) == []


def test_retrieve_treats_empty_filter_as_no_filter(client: TestClient, sample_md: bytes) -> None:
    ingest.ingest_document("sample.md", sample_md)
    assert len(retrieve("planets", document_ids=[])) == 3


def test_retrieve_on_empty_collection_returns_nothing(client: TestClient) -> None:
    assert retrieve("anything") == []
