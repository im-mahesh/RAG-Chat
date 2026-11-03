import pytest

from app.ingest import chunk_text


def test_empty_input_returns_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("  \n\n \t\n") == []


def test_short_text_is_a_single_chunk() -> None:
    chunks = chunk_text("Just one short paragraph.")
    assert [c.text for c in chunks] == ["Just one short paragraph."]
    assert chunks[0].heading is None


def test_invalid_size_or_overlap_is_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_text("text", size=100, overlap=100)
    with pytest.raises(ValueError):
        chunk_text("text", size=0, overlap=0)


def test_long_paragraph_falls_back_to_overlapping_windows() -> None:
    text = "".join(chr(ord("a") + i % 26) for i in range(2000))
    chunks = chunk_text(text, size=800, overlap=100)
    assert len(chunks) == 3
    assert all(len(c.text) <= 800 for c in chunks)
    for current, following in zip(chunks, chunks[1:]):
        assert current.text[-100:] == following.text[:100]
    assert text.startswith(chunks[0].text)
    assert text.endswith(chunks[-1].text)


def test_paragraphs_are_packed_and_overlap_between_chunks() -> None:
    paragraphs = [f"Paragraph {i} " + "word " * 50 for i in range(6)]
    chunks = chunk_text("\n\n".join(paragraphs), size=800, overlap=100)
    assert len(chunks) > 1
    assert all(len(c.text) <= 800 for c in chunks)
    for current, following in zip(chunks, chunks[1:]):
        carried = following.text.split("\n\n")[0]
        assert current.text.endswith(carried)
        assert 0 < len(carried) <= 100


def test_never_splits_a_paragraph_that_fits() -> None:
    paragraphs = ["alpha " * 60, "beta " * 60, "gamma " * 60]
    chunks = chunk_text("\n\n".join(paragraphs), size=400, overlap=50)
    joined = "\n\n".join(c.text for c in chunks)
    for paragraph in paragraphs:
        assert paragraph.strip() in joined


def test_heading_is_carried_into_chunk_metadata() -> None:
    text = "intro text\n\n# Alpha\n\nalpha body\n\n## Beta\n\nbeta body"
    chunks = chunk_text(text)
    assert [(c.heading, c.text) for c in chunks] == [
        (None, "intro text"),
        ("Alpha", "# Alpha\n\nalpha body"),
        ("Beta", "## Beta\n\nbeta body"),
    ]


def test_heading_applies_to_every_chunk_of_a_long_section() -> None:
    body = "\n\n".join("sentence " * 40 for _ in range(8))
    chunks = chunk_text(f"# Long Section\n\n{body}", size=500, overlap=50)
    assert len(chunks) > 2
    assert {c.heading for c in chunks} == {"Long Section"}


def test_heading_only_sections_merge_into_the_next_section() -> None:
    chunks = chunk_text("# Title\n\n## Subtitle\n\nbody text")
    assert len(chunks) == 1
    assert chunks[0].heading == "Subtitle"
    assert chunks[0].text.startswith("# Title")


def test_initial_heading_carries_across_calls() -> None:
    chunks = chunk_text("continued text from the next page", heading="Earlier Heading")
    assert chunks[0].heading == "Earlier Heading"


def test_hash_lines_inside_code_fences_are_not_headings() -> None:
    text = "# Real\n\n```\n# not a heading\n```\n\nafter"
    assert {c.heading for c in chunk_text(text)} == {"Real"}
