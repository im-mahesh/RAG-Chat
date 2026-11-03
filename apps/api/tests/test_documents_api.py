from fastapi.testclient import TestClient

from app import store
from app.main import MAX_UPLOAD_BYTES
from pdf_helper import make_pdf


def upload(client: TestClient, name: str, data: bytes, content_type: str = "text/markdown"):
    return client.post("/documents", files={"file": (name, data, content_type)})


def test_upload_markdown_returns_id_and_chunk_count(client: TestClient, sample_md: bytes) -> None:
    response = upload(client, "sample.md", sample_md)
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "sample.md"
    assert body["chunk_count"] == 3
    assert len(body["id"]) == 36


def test_upload_stores_chunk_metadata(client: TestClient, sample_md: bytes) -> None:
    document_id = upload(client, "sample.md", sample_md).json()["id"]
    stored = store.get_collection().get(where={"document_id": document_id}, include=["metadatas"])
    metas = sorted(stored["metadatas"], key=lambda m: m["chunk_index"])
    assert [m["heading"] for m in metas] == ["Solar System", "Inner Planets", "Outer Planets"]
    assert all(m["filename"] == "sample.md" and "page" not in m for m in metas)


def test_upload_pdf_keeps_page_numbers(client: TestClient) -> None:
    pdf = make_pdf(["Text on page one", "Text on page two"])
    response = upload(client, "paper.pdf", pdf, "application/pdf")
    assert response.status_code == 201
    stored = store.get_collection().get(
        where={"document_id": response.json()["id"]}, include=["metadatas"]
    )
    pages = sorted(m["page"] for m in stored["metadatas"])
    assert pages == [1, 2]


def test_collection_uses_cosine_distance(client: TestClient) -> None:
    config = store.get_collection().configuration
    assert config["hnsw"]["space"] == "cosine"


def test_list_documents_returns_uploads(client: TestClient, sample_md: bytes) -> None:
    assert client.get("/documents").json() == []
    document_id = upload(client, "sample.md", sample_md).json()["id"]
    listed = client.get("/documents").json()
    assert len(listed) == 1
    assert listed[0]["id"] == document_id
    assert listed[0]["filename"] == "sample.md"
    assert listed[0]["chunk_count"] == 3
    assert listed[0]["uploaded_at"]


def test_delete_document_removes_all_its_chunks(client: TestClient, sample_md: bytes) -> None:
    keep = upload(client, "keep.md", sample_md).json()["id"]
    gone = upload(client, "gone.md", sample_md).json()["id"]
    response = client.delete(f"/documents/{gone}")
    assert response.status_code == 200
    assert response.json() == {"id": gone, "deleted_chunks": 3}
    assert [d["id"] for d in client.get("/documents").json()] == [keep]


def test_delete_unknown_document_returns_404(client: TestClient) -> None:
    assert client.delete("/documents/nope").status_code == 404


def test_upload_rejects_unsupported_type(client: TestClient) -> None:
    response = upload(client, "malware.exe", b"MZ", "application/octet-stream")
    assert response.status_code == 400
    assert "Unsupported file type '.exe'" in response.json()["detail"]
    assert client.get("/documents").json() == []


def test_upload_rejects_files_over_10_mb(client: TestClient) -> None:
    response = upload(client, "big.txt", b"a" * (MAX_UPLOAD_BYTES + 1), "text/plain")
    assert response.status_code == 400
    assert "too large" in response.json()["detail"]


def test_upload_rejects_empty_document(client: TestClient) -> None:
    response = upload(client, "empty.txt", b"  \n", "text/plain")
    assert response.status_code == 400
    assert "No text could be extracted" in response.json()["detail"]
