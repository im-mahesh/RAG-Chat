import asyncio
import json

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app import generate, main
from app.retrieve import Chunk
from conftest import FakeAsyncAnthropic


REAL_GET_ASYNC_CLIENT = generate.get_async_client


def upload(client: TestClient, name: str, data: bytes) -> str:
    response = client.post("/documents", files={"file": (name, data, "text/markdown")})
    assert response.status_code == 201
    return response.json()["id"]


def parse_events(body: str) -> list[dict]:
    return [json.loads(block.removeprefix("data: ")) for block in body.split("\n\n") if block]


def stream_chat(client: TestClient, **payload: object):
    payload.setdefault("question", "Which planets are gas giants?")
    return client.post("/chat/stream", json=payload)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeAsyncAnthropic:
    fake = FakeAsyncAnthropic()
    monkeypatch.setattr(generate, "get_async_client", lambda: fake)
    return fake


def rate_limit_error() -> anthropic.RateLimitError:
    response = httpx2.Response(429, request=httpx2.Request("POST", "https://x"))
    return anthropic.RateLimitError("slow down", response=response, body=None)


def test_events_arrive_as_sources_then_tokens_then_done(
    client: TestClient, sample_md: bytes, fake: FakeAsyncAnthropic
) -> None:
    upload(client, "sample.md", sample_md)

    response = stream_chat(client)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    events = parse_events(response.text)
    assert [e["type"] for e in events] == ["sources", "token", "token", "token", "token", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Jupiter and Saturn [1]."
    sources = events[0]["sources"]
    assert len(sources) == 3
    assert set(sources[0]) == {
        "document_id", "text", "filename", "page", "heading", "chunk_index", "score"
    }


def test_stream_prompt_contains_numbered_context(
    client: TestClient, sample_md: bytes, fake: FakeAsyncAnthropic
) -> None:
    upload(client, "sample.md", sample_md)

    stream_chat(client)

    call = fake.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["max_tokens"] == 1024
    assert "[1] (sample.md)\n" in call["messages"][0]["content"]


def test_stream_respects_document_filter(
    client: TestClient, sample_md: bytes, baking_md: bytes, fake: FakeAsyncAnthropic
) -> None:
    upload(client, "sample.md", sample_md)
    baking_id = upload(client, "baking.md", baking_md)

    events = parse_events(stream_chat(client, document_ids=[baking_id]).text)

    assert {s["filename"] for s in events[0]["sources"]} == {"baking.md"}


def test_error_mid_stream_is_an_error_event_after_partial_tokens(
    client: TestClient, sample_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeAsyncAnthropic(error=rate_limit_error(), error_after=2)
    monkeypatch.setattr(generate, "get_async_client", lambda: fake)
    upload(client, "sample.md", sample_md)

    events = parse_events(stream_chat(client).text)

    assert [e["type"] for e in events] == ["sources", "token", "token", "error"]
    assert "rate limit" in events[-1]["message"].lower()


def test_error_when_the_stream_cannot_start_is_an_error_event(
    client: TestClient, sample_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeAsyncAnthropic(error=rate_limit_error())
    monkeypatch.setattr(generate, "get_async_client", lambda: fake)
    upload(client, "sample.md", sample_md)

    events = parse_events(stream_chat(client).text)

    assert [e["type"] for e in events] == ["sources", "error"]


def test_refusal_is_an_error_event_not_done(
    client: TestClient, sample_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeAsyncAnthropic(stop_reason="refusal")
    monkeypatch.setattr(generate, "get_async_client", lambda: fake)
    upload(client, "sample.md", sample_md)

    events = parse_events(stream_chat(client).text)

    assert events[-1] == {"type": "error", "message": "The model declined to answer this question."}
    assert "done" not in [e["type"] for e in events]


def test_empty_stream_is_an_error_event(
    client: TestClient, sample_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generate, "get_async_client", lambda: FakeAsyncAnthropic(tokens=[]))
    upload(client, "sample.md", sample_md)

    events = parse_events(stream_chat(client).text)

    assert [e["type"] for e in events] == ["sources", "error"]


def test_failures_before_streaming_are_plain_http_errors(
    client: TestClient, sample_md: bytes, fake: FakeAsyncAnthropic, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert stream_chat(client).status_code == 409  # nothing indexed yet
    upload(client, "sample.md", sample_md)
    assert stream_chat(client, document_ids=["nope"]).status_code == 404
    assert stream_chat(client, question="  ").status_code == 422
    assert fake.calls == []

    monkeypatch.setattr(generate, "get_async_client", REAL_GET_ASYNC_CLIENT)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = stream_chat(client)
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


class FakeHttpRequest:
    """Reports a disconnect once is_disconnected() has been called more than `after` times."""

    def __init__(self, after: int):
        self.after = after
        self.checks = 0

    async def is_disconnected(self) -> bool:
        self.checks += 1
        return self.checks > self.after


def test_generation_stops_and_stream_closes_when_the_client_disconnects() -> None:
    fake = FakeAsyncAnthropic(tokens=[f"t{i}" for i in range(10)])
    chunk = Chunk(document_id="d", text="x", filename="a.md", chunk_index=0, score=0.5)

    async def collect() -> list[dict]:
        events = main._stream_events(FakeHttpRequest(after=2), "q", [chunk], fake)  # type: ignore[arg-type]
        return [json.loads(e.removeprefix("data: ")) for e in [e async for e in events]]

    events = asyncio.run(collect())

    assert [e["type"] for e in events] == ["sources", "token", "token"]
    stream = fake.streams[0]
    assert stream.closed
    assert stream.pulled < 10
