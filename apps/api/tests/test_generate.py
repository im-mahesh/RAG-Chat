import anthropic
import httpx2
import pytest

from app import generate
from app.generate import GenerationError, answer, build_context
from app.retrieve import Chunk
from conftest import FakeAnthropic


def make_chunk(filename: str, text: str, page: int | None = None) -> Chunk:
    return Chunk(
        document_id="doc", text=text, filename=filename, page=page, chunk_index=0, score=0.9
    )


CHUNKS = [
    make_chunk("report.pdf", "Revenue grew 12% in 2024.", page=3),
    make_chunk("notes.md", "The launch is planned for May."),
]


def status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request)
    return cls("boom", response=response, body=None)


def test_context_is_numbered_with_filename_and_page() -> None:
    assert build_context(CHUNKS) == (
        "[1] (report.pdf, page 3)\nRevenue grew 12% in 2024.\n\n"
        "[2] (notes.md)\nThe launch is planned for May."
    )


def test_answer_sends_numbered_context_and_question() -> None:
    fake = FakeAnthropic(reply="Revenue grew 12% [1].")

    result = answer("How much did revenue grow?", CHUNKS, client=fake)

    assert result == "Revenue grew 12% [1]."
    call = fake.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["max_tokens"] == 1024
    [message] = call["messages"]
    assert message["role"] == "user"
    assert "[1] (report.pdf, page 3)\nRevenue grew 12% in 2024." in message["content"]
    assert "[2] (notes.md)\nThe launch is planned for May." in message["content"]
    assert message["content"].endswith("Question: How much did revenue grow?")


def test_system_prompt_states_grounding_and_citation_rules() -> None:
    fake = FakeAnthropic()
    answer("q", CHUNKS, client=fake)
    system = fake.calls[0]["system"]
    assert "only from the provided context" in system
    assert "[1], [2]" in system
    assert "I don't know based on the provided documents." in system
    assert "Never invent citations" in system


def test_missing_api_key_raises_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(GenerationError, match="ANTHROPIC_API_KEY") as info:
        generate.get_client()
    assert info.value.status_code == 503


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (status_error(anthropic.RateLimitError, 429), 429),
        (status_error(anthropic.AuthenticationError, 401), 502),
        (status_error(anthropic.InternalServerError, 500), 502),
        (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")), 503),
        (anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")), 504),
    ],
)
def test_anthropic_errors_map_to_http_statuses(error: Exception, status: int) -> None:
    with pytest.raises(GenerationError) as info:
        answer("q", CHUNKS, client=FakeAnthropic(error=error))
    assert info.value.status_code == status


def test_empty_model_reply_is_an_error() -> None:
    with pytest.raises(GenerationError, match="empty answer"):
        answer("q", CHUNKS, client=FakeAnthropic(reply="  "))
