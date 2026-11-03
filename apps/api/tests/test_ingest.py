import numpy as np
import pytest

from app import ingest
from app.ingest import IngestError, extract_text
from pdf_helper import make_pdf


def test_extract_text_reads_markdown_and_txt() -> None:
    for name in ("notes.md", "NOTES.TXT"):
        pages = extract_text(name, "héllo\nworld".encode())
        assert [(p.text, p.page) for p in pages] == [("héllo\nworld", None)]


def test_extract_text_strips_utf8_bom() -> None:
    pages = extract_text("a.txt", b"\xef\xbb\xbfhello")
    assert pages[0].text == "hello"


def test_extract_text_returns_one_entry_per_pdf_page() -> None:
    pages = extract_text("doc.pdf", make_pdf(["First page text", "Second page text"]))
    assert [p.page for p in pages] == [1, 2]
    assert "First page text" in pages[0].text
    assert "Second page text" in pages[1].text


def test_extract_text_rejects_unsupported_extension() -> None:
    with pytest.raises(IngestError, match="Unsupported file type '.exe'"):
        extract_text("virus.exe", b"MZ")


def test_extract_text_rejects_a_file_that_is_not_a_pdf() -> None:
    with pytest.raises(IngestError, match="not a valid PDF"):
        extract_text("renamed.pdf", b"this is not a pdf")


def test_extract_text_rejects_a_pdf_with_a_valid_header_but_broken_body() -> None:
    with pytest.raises(IngestError, match="Could not read the PDF"):
        extract_text("broken.pdf", b"%PDF-1.4\ngarbage that is not a real document")


@pytest.mark.parametrize("error", [ValueError("x"), KeyError("y"), RecursionError()])
def test_unexpected_pypdf_failures_become_a_clean_error_not_a_500(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def explode(*_args: object) -> None:
        raise error

    monkeypatch.setattr(ingest, "PdfReader", explode)
    with pytest.raises(IngestError, match="Could not read the PDF"):
        extract_text("weird.pdf", b"%PDF-1.4\n")


def test_encrypted_pdfs_are_rejected_with_their_own_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class Encrypted:
        is_encrypted = True
        pages: list[object] = []

    monkeypatch.setattr(ingest, "PdfReader", lambda *_args: Encrypted())
    with pytest.raises(IngestError, match="Encrypted PDFs"):
        extract_text("locked.pdf", b"%PDF-1.4\n")


def test_extract_text_rejects_binary_files_renamed_to_text() -> None:
    for name in ("photo.txt", "archive.md"):
        with pytest.raises(IngestError, match="binary file"):
            extract_text(name, b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")


def test_embed_uses_normalized_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeModel:
        def encode(self, texts: list[str], **kwargs: object) -> np.ndarray:
            calls.append(kwargs)
            return np.ones((len(texts), 3))

    monkeypatch.setattr(ingest, "get_model", lambda: FakeModel())
    vectors = ingest.embed(["a", "b"])
    assert vectors == [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]
    assert calls[0]["normalize_embeddings"] is True
