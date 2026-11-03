from eval import run
from eval.run import Question, first_hit_rank, format_table, is_hit
from app.retrieve import Chunk


def chunk(filename: str, text: str = "text") -> Chunk:
    return Chunk(document_id="d", text=text, filename=filename, chunk_index=0, score=0.5)


def test_hit_requires_the_expected_file() -> None:
    question = Question(question="q", expected_filename="a.md")
    assert is_hit(chunk("a.md"), question)
    assert not is_hit(chunk("b.md"), question)


def test_snippet_match_ignores_case_and_whitespace() -> None:
    question = Question(
        question="q", expected_filename="a.md", expected_text_snippet="within 30 days of the purchase"
    )
    assert is_hit(chunk("a.md", "Submit  within\n30 DAYS of the purchase date"), question)
    assert not is_hit(chunk("a.md", "within 60 days"), question)
    assert not is_hit(chunk("b.md", "within 30 days of the purchase"), question)


def test_first_hit_rank_is_one_based_or_none() -> None:
    question = Question(question="q", expected_filename="a.md", expected_text_snippet="needle")
    chunks = [chunk("a.md", "hay"), chunk("b.md", "needle"), chunk("a.md", "a needle here")]
    assert first_hit_rank(chunks, question) == 3
    assert first_hit_rank(chunks[:2], question) is None
    assert first_hit_rank([], question) is None


def test_table_lists_every_mode_with_its_metrics() -> None:
    results = [
        run.ModeResult(name="vector", hit_at_1=0.75, hit_at_k=1.0, mrr=0.875, ms_per_query=5, not_first=[]),
        run.ModeResult(name="hybrid", hit_at_1=0.85, hit_at_k=1.0, mrr=0.925, ms_per_query=4, not_first=[]),
    ]
    table = format_table(results, k=5, n_questions=20)
    assert "20 questions" in table and "hit@5" in table and "MRR@5" in table
    assert "vector" in table and "0.875" in table and "0.925" in table


def test_every_question_points_at_a_real_doc_that_contains_its_snippet() -> None:
    questions = run.load_questions()
    assert 15 <= len(questions) <= 20
    docs = {p.name: run.normalize(p.read_text()) for p in (run.EVAL_DIR / "docs").iterdir()}
    for q in questions:
        assert q.expected_filename in docs, q.question
        if q.expected_text_snippet:
            assert run.normalize(q.expected_text_snippet) in docs[q.expected_filename], q.question
