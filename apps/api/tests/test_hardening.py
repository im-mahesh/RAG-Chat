import json
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app import generate, main
from app.main import MAX_UPLOAD_BYTES, MULTIPART_OVERHEAD_BYTES, RateLimiter
from app.retrieve import RetrievalSettings
from conftest import FakeAnthropic, FakeAsyncAnthropic


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def upload(client: TestClient, name: str, data: bytes, **kwargs: object):
    return client.post("/documents", files={"file": (name, data, "text/plain")}, **kwargs)


# --- RateLimiter --------------------------------------------------------------


def test_limiter_allows_up_to_the_limit_then_reports_the_wait() -> None:
    clock = Clock()
    limiter = RateLimiter(3, 60, clock)

    assert [limiter.check("a") for _ in range(3)] == [None, None, None]
    assert limiter.check("a") == pytest.approx(60)

    clock.now += 45
    assert limiter.check("a") == pytest.approx(15)  # the oldest hit expires in 15 s

    clock.now += 15.1
    assert limiter.check("a") is None


def test_limiter_is_a_sliding_window_not_a_fixed_bucket() -> None:
    clock = Clock()
    limiter = RateLimiter(2, 60, clock)
    limiter.check("a")  # t=0
    clock.now += 40
    limiter.check("a")  # t=40
    clock.now += 21  # t=61: the first hit has expired, the second has not

    assert limiter.check("a") is None
    assert limiter.check("a") == pytest.approx(39)


def test_limiter_keeps_clients_apart_and_can_be_disabled() -> None:
    limiter = RateLimiter(1)
    assert limiter.check("a") is None
    assert limiter.check("a") is not None
    assert limiter.check("b") is None

    off = RateLimiter(0)
    assert all(off.check("a") is None for _ in range(100))


def test_limiter_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "7")
    assert RateLimiter.from_env().limit == 7
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "lots")
    with pytest.raises(ValueError, match="RATE_LIMIT_PER_MINUTE"):
        RateLimiter.from_env()


def test_limiter_forgets_idle_clients() -> None:
    clock = Clock()
    limiter = RateLimiter(5, 60, clock)
    for i in range(1100):
        limiter.check(f"client-{i}")
    clock.now += 61

    limiter.check("newcomer")

    assert len(limiter._hits) == 1


# --- rate limiting the chat endpoints ------------------------------------------


@pytest.fixture
def two_per_minute(monkeypatch: pytest.MonkeyPatch) -> RateLimiter:
    limiter = RateLimiter(2)
    monkeypatch.setattr(main, "chat_limiter", limiter)
    return limiter


def test_stream_endpoint_returns_429_with_retry_after_once_the_limit_is_hit(
    client: TestClient, sample_md: bytes, two_per_minute: RateLimiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeAsyncAnthropic()
    monkeypatch.setattr(generate, "get_async_client", lambda: fake)
    upload(client, "sample.md", sample_md)

    statuses = [client.post("/chat/stream", json={"question": "planets?"}).status_code for _ in range(3)]
    blocked = client.post("/chat/stream", json={"question": "planets?"})

    assert statuses == [200, 200, 429]
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert "Too many requests" in blocked.json()["detail"]
    assert len(fake.streams) == 2  # the blocked requests never reached the model


def test_non_streaming_chat_shares_the_same_limit(
    client: TestClient, sample_md: bytes, two_per_minute: RateLimiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generate, "get_client", lambda: FakeAnthropic())
    upload(client, "sample.md", sample_md)

    statuses = [client.post("/chat", json={"question": "planets?"}).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def test_other_endpoints_are_not_rate_limited(client: TestClient, two_per_minute: RateLimiter) -> None:
    assert all(client.get("/documents").status_code == 200 for _ in range(10))
    assert all(client.get("/health").status_code == 200 for _ in range(10))


# --- upload checks -------------------------------------------------------------


def test_oversized_upload_is_rejected_early_and_still_carries_cors_headers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object) -> None:
        raise AssertionError("the body should never reach the endpoint")

    monkeypatch.setattr(main.ingest, "ingest_document", explode)
    big = b"a" * (MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES + 1024)

    response = upload(client, "big.txt", big, headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 400
    assert "too large" in response.json()["detail"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_upload_just_over_the_limit_is_still_rejected_by_the_endpoint(client: TestClient) -> None:
    response = upload(client, "big.txt", b"a" * (MAX_UPLOAD_BYTES + 1))
    assert response.status_code == 400
    assert "too large" in response.json()["detail"]


def test_upload_rejects_binary_content_with_a_text_extension(client: TestClient) -> None:
    response = upload(client, "photo.txt", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    assert response.status_code == 400
    assert "binary" in response.json()["detail"]


def test_upload_rejects_a_fake_pdf(client: TestClient) -> None:
    response = upload(client, "report.pdf", b"<html>definitely not a pdf</html>")
    assert response.status_code == 400
    assert "not a valid PDF" in response.json()["detail"]


# --- configuration -------------------------------------------------------------


def test_cors_origins_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert main.cors_origins() == ["http://localhost:5173"]
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example ,")
    assert main.cors_origins() == ["https://a.example", "https://b.example"]


def test_candidate_count_must_be_a_positive_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    for bad in ("abc", "0", "-3", "2.5"):
        monkeypatch.setenv("RETRIEVAL_CANDIDATES", bad)
        with pytest.raises(ValueError, match="RETRIEVAL_CANDIDATES"):
            RetrievalSettings.from_env()


# --- unexpected errors while streaming -----------------------------------------


def test_an_unexpected_error_mid_stream_becomes_an_error_event(
    client: TestClient, sample_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken_stream(*_args: object) -> AsyncIterator[str]:
        yield "partial "
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(generate, "get_async_client", lambda: FakeAsyncAnthropic())
    monkeypatch.setattr(generate, "stream_answer", broken_stream)
    upload(client, "sample.md", sample_md)

    response = client.post("/chat/stream", json={"question": "planets?"})

    events = [json.loads(b.removeprefix("data: ")) for b in response.text.split("\n\n") if b]
    assert [e["type"] for e in events] == ["sources", "token", "error"]
    assert events[-1]["message"] == "Something went wrong while generating the answer."
    assert "secret internal detail" not in response.text
