from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import ingest, main, store
from app.generate import REWRITE_MODEL
from app.main import app

FIXTURES = Path(__file__).parent / "fixtures"
KEYWORDS = ("planet", "sun", "giant", "bread", "flour", "oven")


def fake_embed(texts: list[str]) -> list[list[float]]:
    """Keyword-count vectors, so similar topics are close under cosine distance."""
    return [[float(t.lower().count(k)) for k in KEYWORDS] + [0.1] for t in texts]


def _text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")


class FakeAnthropic:
    """Stands in for anthropic.Anthropic; records calls to messages.create.

    Query-rewrite calls (made with the rewrite model) get `rewrite_reply` or
    raise `rewrite_error`; every other call gets `reply` or raises `error`.
    """

    def __init__(
        self,
        reply: str = "Mocked answer [1].",
        error: Exception | None = None,
        rewrite_reply: str = "standalone question",
        rewrite_error: Exception | None = None,
    ):
        self.calls: list[dict[str, Any]] = []
        self.reply = reply
        self.error = error
        self.rewrite_reply = rewrite_reply
        self.rewrite_error = rewrite_error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        is_rewrite = kwargs["model"] == REWRITE_MODEL
        error = self.rewrite_error if is_rewrite else self.error
        if error:
            raise error
        return _text_response(self.rewrite_reply if is_rewrite else self.reply)

    @property
    def answer_calls(self) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["model"] != REWRITE_MODEL]

    @property
    def rewrite_calls(self) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["model"] == REWRITE_MODEL]


class FakeStream:
    """Mimics anthropic's AsyncMessageStream; records how far it was consumed and closed."""

    def __init__(
        self,
        tokens: list[str],
        error: Exception | None = None,
        error_after: int | None = None,
        stop_reason: str = "end_turn",
    ):
        self.tokens = tokens
        self.error = error
        self.error_after = error_after
        self.stop_reason = stop_reason
        self.pulled = 0
        self.closed = False
        self.text_stream = self._text()

    async def _text(self) -> AsyncIterator[str]:
        for index, token in enumerate(self.tokens):
            if self.error and index == self.error_after:
                raise self.error
            self.pulled += 1
            yield token

    async def __aenter__(self) -> "FakeStream":
        if self.error and self.error_after is None:
            raise self.error
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.closed = True

    async def get_final_message(self) -> SimpleNamespace:
        return SimpleNamespace(stop_reason=self.stop_reason)


class FakeAsyncAnthropic:
    """Stands in for anthropic.AsyncAnthropic; records stream() calls and streams."""

    def __init__(
        self,
        tokens: list[str] | None = None,
        rewrite_reply: str = "standalone question",
        **stream_options: Any,
    ):
        self.tokens = ["Jupiter", " and", " Saturn", " [1]."] if tokens is None else tokens
        self.rewrite_reply = rewrite_reply
        self.stream_options = stream_options
        self.calls: list[dict[str, Any]] = []
        self.rewrite_calls: list[dict[str, Any]] = []
        self.streams: list[FakeStream] = []
        self.messages = SimpleNamespace(stream=self._stream, create=self._create)

    async def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.rewrite_calls.append(kwargs)
        return _text_response(self.rewrite_reply)

    def _stream(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        stream = FakeStream(self.tokens, **self.stream_options)
        self.streams.append(stream)
        return stream


@pytest.fixture(autouse=True)
def pinned_retrieval_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plain vector search, no reranker: tests never depend on the app's defaults or load models."""
    monkeypatch.setenv("RETRIEVAL_MODE", "vector")
    monkeypatch.setenv("RERANK", "false")


@pytest.fixture(autouse=True)
def fresh_rate_limiter() -> None:
    """The limiter is process-wide; without this the whole suite would share one budget."""
    main.chat_limiter.reset()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(ingest, "embed", fake_embed)
    store.get_collection.cache_clear()
    yield TestClient(app)
    store.get_collection.cache_clear()


@pytest.fixture
def sample_md() -> bytes:
    return (FIXTURES / "sample.md").read_bytes()


@pytest.fixture
def baking_md() -> bytes:
    return (FIXTURES / "baking.md").read_bytes()
