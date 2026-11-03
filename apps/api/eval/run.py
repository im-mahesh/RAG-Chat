"""Retrieval evaluation harness.

Ingests eval/docs into a throwaway Chroma store, runs every question in
eval/questions.json through each retrieval configuration, and prints hit@k and
MRR@k. Run from apps/api:

    uv run python -m eval.run [--modes vector hybrid ...] [--k 5] [--verbose]

The first run downloads the cross-encoder (~90 MB) if it isn't cached.
"""

import argparse
import json
import os
import re
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel

from app import ingest, retrieve, store
from app.retrieve import Chunk, RetrievalSettings

EVAL_DIR = Path(__file__).parent

CONFIGS: dict[str, RetrievalSettings] = {
    "vector": RetrievalSettings(mode="vector", rerank=False),
    "hybrid": RetrievalSettings(mode="hybrid", rerank=False),
    "vector+rerank": RetrievalSettings(mode="vector", rerank=True),
    "hybrid+rerank": RetrievalSettings(mode="hybrid", rerank=True),
}


class Question(BaseModel):
    question: str
    expected_filename: str
    expected_text_snippet: str | None = None


class ModeResult(BaseModel):
    name: str
    hit_at_1: float
    hit_at_k: float
    mrr: float
    ms_per_query: float
    not_first: list[str]


# --- metrics ----------------------------------------------------------------


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def is_hit(chunk: Chunk, question: Question) -> bool:
    """A chunk is a hit if it is from the expected file and contains the snippet (if any)."""
    if chunk.filename != question.expected_filename:
        return False
    snippet = question.expected_text_snippet
    return snippet is None or normalize(snippet) in normalize(chunk.text)


def first_hit_rank(chunks: list[Chunk], question: Question) -> int | None:
    """1-based rank of the first hit, or None if there isn't one."""
    for rank, chunk in enumerate(chunks, start=1):
        if is_hit(chunk, question):
            return rank
    return None


# --- setup ------------------------------------------------------------------


def load_questions() -> list[Question]:
    raw = json.loads((EVAL_DIR / "questions.json").read_text())
    return [Question(**item) for item in raw]


def ingest_docs() -> int:
    total = 0
    for path in sorted((EVAL_DIR / "docs").iterdir()):
        total += ingest.ingest_document(path.name, path.read_bytes()).chunk_count
    return total


def validate_questions(questions: list[Question]) -> None:
    """Fail early if an expected snippet doesn't exist in its file's chunks."""
    chunks = store.all_chunks()
    problems = [
        q.question
        for q in questions
        if not any(
            c.metadata.filename == q.expected_filename
            and (
                q.expected_text_snippet is None
                or normalize(q.expected_text_snippet) in normalize(c.text)
            )
            for c in chunks
        )
    ]
    if problems:
        raise SystemExit("Expected text not found in any chunk for:\n  " + "\n  ".join(problems))


# --- evaluation -------------------------------------------------------------


def evaluate(name: str, questions: list[Question], k: int) -> ModeResult:
    settings = CONFIGS[name]
    retrieve.retrieve(questions[0].question, k=k, settings=settings)  # warm-up, not timed
    ranks: list[int | None] = []
    not_first: list[str] = []
    started = time.perf_counter()
    for question in questions:
        chunks = retrieve.retrieve(question.question, k=k, settings=settings)
        rank = first_hit_rank(chunks, question)
        ranks.append(rank)
        if rank != 1:
            got = ", ".join(c.filename for c in chunks[:3])
            not_first.append(
                f"rank {rank or f'>{k}'}: {question.question}  "
                f"[expected {question.expected_filename}; top 3: {got}]"
            )
    elapsed_ms = (time.perf_counter() - started) * 1000
    n = len(questions)
    return ModeResult(
        name=name,
        hit_at_1=sum(r == 1 for r in ranks) / n,
        hit_at_k=sum(r is not None for r in ranks) / n,
        mrr=sum(1 / r for r in ranks if r) / n,
        ms_per_query=elapsed_ms / n,
        not_first=not_first,
    )


def format_table(results: list[ModeResult], k: int, n_questions: int) -> str:
    header = f"{'mode':<16}{'hit@1':>8}{f'hit@{k}':>8}{f'MRR@{k}':>8}{'ms/query':>10}"
    rows = [
        f"{r.name:<16}{r.hit_at_1:>8.2f}{r.hit_at_k:>8.2f}{r.mrr:>8.3f}{r.ms_per_query:>10.0f}"
        for r in results
    ]
    rule = "-" * len(header)
    return "\n".join([f"{n_questions} questions", rule, header, rule, *rows, rule])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality.")
    parser.add_argument("--modes", nargs="+", choices=list(CONFIGS), default=list(CONFIGS))
    parser.add_argument("--k", type=int, default=5, help="cutoff for hit@k and MRR@k")
    parser.add_argument("--verbose", action="store_true", help="list the questions each mode did not rank first")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    questions = load_questions()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CHROMA_PATH"] = tmp  # never touch the real data/chroma
        store.get_collection.cache_clear()
        print(f"Ingested {ingest_docs()} chunks from eval/docs")
        validate_questions(questions)
        results = [evaluate(name, questions, args.k) for name in args.modes]
        store.get_collection.cache_clear()
    print()
    print(format_table(results, args.k, len(questions)))
    if args.verbose:
        for result in results:
            print(f"\n{result.name}: {len(result.not_first)} question(s) not ranked first")
            for line in result.not_first:
                print(f"  - {line}")


if __name__ == "__main__":
    main()
