import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app import generate
from conftest import FakeAnthropic


def upload(client: TestClient, name: str, data: bytes) -> str:
    response = client.post("/documents", files={"file": (name, data, "text/markdown")})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def fake_anthropic(monkeypatch: pytest.MonkeyPatch) -> FakeAnthropic:
    fake = FakeAnthropic(reply="Jupiter and Saturn are gas giants [1].")
    monkeypatch.setattr(generate, "get_client", lambda: fake)
    return fake


def test_chat_returns_answer_and_sources(
    client: TestClient, sample_md: bytes, fake_anthropic: FakeAnthropic
) -> None:
    upload(client, "sample.md", sample_md)

    response = client.post("/chat", json={"question": "Which planets are gas giants?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Jupiter and Saturn are gas giants [1]."
    assert len(body["sources"]) == 3
    top = body["sources"][0]
    assert set(top) == {
        "document_id", "text", "filename", "page", "heading", "chunk_index", "score"
    }
    assert top["filename"] == "sample.md"


def test_chat_prompt_contains_numbered_context_from_retrieval(
    client: TestClient, sample_md: bytes, fake_anthropic: FakeAnthropic
) -> None:
    upload(client, "sample.md", sample_md)

    client.post("/chat", json={"question": "Which planets are gas giants?"})

    prompt = fake_anthropic.calls[0]["messages"][0]["content"]
    assert "[1] (sample.md)\n" in prompt
    assert "[3] (sample.md)\n" in prompt
    assert "Question: Which planets are gas giants?" in prompt


def test_chat_filters_by_document_ids(
    client: TestClient, sample_md: bytes, baking_md: bytes, fake_anthropic: FakeAnthropic
) -> None:
    upload(client, "sample.md", sample_md)
    baking_id = upload(client, "baking.md", baking_md)

    response = client.post(
        "/chat", json={"question": "Which planets are giants?", "document_ids": [baking_id]}
    )

    assert {s["filename"] for s in response.json()["sources"]} == {"baking.md"}


def test_chat_with_no_documents_returns_409(
    client: TestClient, fake_anthropic: FakeAnthropic
) -> None:
    response = client.post("/chat", json={"question": "anything?"})
    assert response.status_code == 409
    assert "No documents have been indexed" in response.json()["detail"]
    assert fake_anthropic.calls == []


def test_chat_with_unknown_document_ids_returns_404(
    client: TestClient, sample_md: bytes, fake_anthropic: FakeAnthropic
) -> None:
    upload(client, "sample.md", sample_md)
    response = client.post("/chat", json={"question": "planets?", "document_ids": ["nope"]})
    assert response.status_code == 404
    assert fake_anthropic.calls == []


def test_chat_without_api_key_returns_503(
    client: TestClient, sample_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    upload(client, "sample.md", sample_md)
    response = client.post("/chat", json={"question": "planets?"})
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_chat_maps_anthropic_rate_limit_to_429(
    client: TestClient, sample_md: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    response_429 = httpx2.Response(429, request=httpx2.Request("POST", "https://x"))
    error = anthropic.RateLimitError("slow down", response=response_429, body=None)
    monkeypatch.setattr(generate, "get_client", lambda: FakeAnthropic(error=error))
    upload(client, "sample.md", sample_md)

    response = client.post("/chat", json={"question": "planets?"})

    assert response.status_code == 429
    assert "rate limit" in response.json()["detail"].lower()


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "   "}])
def test_chat_rejects_blank_questions(client: TestClient, body: dict) -> None:
    assert client.post("/chat", json=body).status_code == 422
