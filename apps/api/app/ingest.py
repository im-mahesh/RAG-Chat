import io
import re
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import PurePath
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pypdf import PdfReader

from app import store

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
SUPPORTED_EXTENSIONS = (".pdf", ".md", ".txt")
PDF_MAGIC = b"%PDF-"
BINARY_SNIFF_BYTES = 1024
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")

Section = tuple[str | None, list[str]]
Piece = tuple[str, bool]  # (text, continues the previous piece's window)


class IngestError(ValueError):
    """The uploaded document can't be ingested; the message is safe to show users."""


class PageText(BaseModel):
    text: str
    page: int | None = None


class TextChunk(BaseModel):
    text: str
    heading: str | None = None
    page: int | None = None


class IngestResult(BaseModel):
    document_id: str
    chunk_count: int


# --- extraction -------------------------------------------------------------


def extract_text(filename: str, data: bytes) -> list[PageText]:
    suffix = PurePath(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(data)
    if suffix in (".md", ".txt"):
        return _extract_plain_text(data)
    allowed = ", ".join(SUPPORTED_EXTENSIONS)
    raise IngestError(f"Unsupported file type '{suffix or filename}'. Allowed: {allowed}.")


def _extract_plain_text(data: bytes) -> list[PageText]:
    # The extension isn't proof of content: a renamed binary has NUL bytes, real text doesn't.
    if b"\x00" in data[:BINARY_SNIFF_BYTES]:
        raise IngestError("The file looks like a binary file, not text.")
    return [PageText(text=data.decode("utf-8-sig", errors="replace"))]


def _extract_pdf(data: bytes) -> list[PageText]:
    if PDF_MAGIC not in data[:BINARY_SNIFF_BYTES]:
        raise IngestError("The file is not a valid PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        encrypted = reader.is_encrypted
        texts = [] if encrypted else [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises many exception types on malformed input
        raise IngestError("Could not read the PDF; the file may be corrupt.") from exc
    if encrypted:
        raise IngestError("Encrypted PDFs are not supported.")
    return [PageText(text=t, page=n) for n, t in enumerate(texts, start=1) if t.strip()]


# --- chunking ---------------------------------------------------------------


def chunk_text(
    text: str, size: int = 800, overlap: int = 100, heading: str | None = None
) -> list[TextChunk]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("size must be positive and overlap must be in [0, size).")
    chunks: list[TextChunk] = []
    for section_heading, blocks in _split_sections(text, heading):
        pieces = [p for block in blocks for p in _split_block(block, size, overlap)]
        chunks += [
            TextChunk(text=t, heading=section_heading)
            for t in _pack_pieces(pieces, size, overlap)
        ]
    return chunks


def _split_sections(text: str, heading: str | None) -> list[Section]:
    """Split into (heading, paragraphs) sections; a heading starts a new section."""
    sections: list[Section] = [(heading, [])]
    lines: list[str] = []
    in_fence = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        match = None if in_fence else HEADING_RE.match(line)
        if match:
            _flush_paragraph(sections, lines)
            carried = _take_lone_heading(sections)
            sections.append((match.group(1), [*carried, line.strip()]))
        elif not in_fence and not line.strip():
            _flush_paragraph(sections, lines)
        else:
            lines.append(line)
    _flush_paragraph(sections, lines)
    return [s for s in sections if s[1]]


def _flush_paragraph(sections: list[Section], lines: list[str]) -> None:
    paragraph = "\n".join(lines).strip()
    if paragraph:
        sections[-1][1].append(paragraph)
    lines.clear()


def _take_lone_heading(sections: list[Section]) -> list[str]:
    """Pop a trailing section holding only its heading so it merges into the next one."""
    heading, blocks = sections[-1]
    if heading is not None and len(blocks) == 1 and HEADING_RE.match(blocks[0]):
        sections.pop()
        return blocks
    return []


def _split_block(block: str, size: int, overlap: int) -> list[Piece]:
    """Return the block whole, or as overlapping character windows if it exceeds size."""
    if len(block) <= size:
        return [(block, False)]
    step = size - overlap
    starts = range(0, len(block) - overlap, step)
    windows = [block[i : i + size] for i in starts]
    return [(w, i > 0) for i, w in enumerate(windows) if w.strip()]


def _pack_pieces(pieces: list[Piece], size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece, continues in pieces:
        if current and len(current) + 2 + len(piece) <= size:
            current = f"{current}\n\n{piece}"
            continue
        if current:
            chunks.append(current)
        tail = "" if continues or not chunks else _overlap_tail(chunks[-1], overlap)
        current = _join_tail(tail, piece, size)
    if current:
        chunks.append(current)
    return chunks


def _overlap_tail(previous: str, overlap: int) -> str:
    """Last `overlap` characters of the previous chunk, trimmed to start at a word."""
    start = max(len(previous) - overlap, 0)
    while 0 < start < len(previous) and not previous[start - 1].isspace():
        start += 1
    return previous[start:].strip()


def _join_tail(tail: str, piece: str, size: int) -> str:
    if tail and len(tail) + 2 + len(piece) <= size:
        return f"{tail}\n\n{piece}"
    return piece


# --- embedding --------------------------------------------------------------


@lru_cache(maxsize=1)
def get_model() -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    vectors = get_model().encode(texts, normalize_embeddings=True, batch_size=32)
    return vectors.tolist()


# --- pipeline ---------------------------------------------------------------


def ingest_document(filename: str, data: bytes) -> IngestResult:
    filename = PurePath(filename).name
    chunks = _chunk_pages(extract_text(filename, data))
    if not chunks:
        raise IngestError(f"No text could be extracted from '{filename}'.")
    document_id = str(uuid.uuid4())
    embeddings = embed([c.text for c in chunks])
    uploaded_at = datetime.now(UTC).isoformat()
    store.add_chunks(
        [
            _to_stored_chunk(document_id, filename, uploaded_at, i, chunk, vector)
            for i, (chunk, vector) in enumerate(zip(chunks, embeddings, strict=True))
        ]
    )
    return IngestResult(document_id=document_id, chunk_count=len(chunks))


def _chunk_pages(pages: list[PageText]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    heading: str | None = None
    for page in pages:
        page_chunks = chunk_text(page.text, heading=heading)
        chunks += [c.model_copy(update={"page": page.page}) for c in page_chunks]
        if page_chunks:
            heading = page_chunks[-1].heading
    return chunks


def _to_stored_chunk(
    document_id: str,
    filename: str,
    uploaded_at: str,
    index: int,
    chunk: TextChunk,
    embedding: list[float],
) -> store.StoredChunk:
    return store.StoredChunk(
        id=f"{document_id}:{index}",
        text=chunk.text,
        embedding=embedding,
        metadata=store.ChunkMetadata(
            document_id=document_id,
            filename=filename,
            chunk_index=index,
            uploaded_at=uploaded_at,
            page=chunk.page,
            heading=chunk.heading,
        ),
    )
