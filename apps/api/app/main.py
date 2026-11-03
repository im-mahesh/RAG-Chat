import logging
import math
import os
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing, asynccontextmanager
from pathlib import PurePath
from typing import Annotated, Literal

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, RootModel, StringConstraints
from starlette.types import ASGIApp, Receive, Scope, Send

from app import generate, ingest, retrieve, store

load_dotenv()

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MULTIPART_OVERHEAD_BYTES = 64 * 1024  # boundaries and headers around the file in the request body
DEFAULT_CHAT_LIMIT_PER_MINUTE = 20


def too_large_message() -> str:
    return f"File is too large. The maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."


class UploadSizeLimitMiddleware:
    """Rejects an oversized POST /documents from its Content-Length header, before the body is read.

    The endpoint still checks the real size, which also covers chunked uploads
    that send no Content-Length. This is plain ASGI (not BaseHTTPMiddleware) so
    it doesn't interfere with streaming responses or disconnect detection.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == "/documents":
            length = dict(scope["headers"]).get(b"content-length", b"")
            if length.isdigit() and int(length) > MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES:
                response = JSONResponse({"detail": too_large_message()}, status_code=400)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class RateLimiter:
    """Sliding-window limiter keyed by client. In-process, so the limit applies per server process."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    @classmethod
    def from_env(cls) -> "RateLimiter":
        """RATE_LIMIT_PER_MINUTE requests per client per minute; 0 turns the limit off."""
        raw = os.environ.get("RATE_LIMIT_PER_MINUTE", str(DEFAULT_CHAT_LIMIT_PER_MINUTE))
        if not raw.strip().isdigit():
            raise ValueError(f"RATE_LIMIT_PER_MINUTE must be a whole number, got {raw!r}.")
        return cls(int(raw))

    def check(self, key: str) -> float | None:
        """Record a request. Returns None if allowed, else the seconds until one would be."""
        if self.limit == 0:
            return None
        now = self._clock()
        self._forget_idle_clients(now)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return hits[0] + self.window - now
        hits.append(now)
        return None

    def _forget_idle_clients(self, now: float) -> None:
        if len(self._hits) < 1024:
            return
        idle = [k for k, hits in self._hits.items() if not hits or hits[-1] <= now - self.window]
        for key in idle:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


chat_limiter = RateLimiter.from_env()


def enforce_chat_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    retry_after = chat_limiter.check(client)
    if retry_after is not None:
        seconds = max(1, math.ceil(retry_after))
        raise HTTPException(
            429,
            f"Too many requests. Try again in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )


def cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = retrieve.RetrievalSettings.from_env()  # fail fast on a bad setting
    await run_in_threadpool(ingest.get_model)
    await run_in_threadpool(retrieve.warm_up, settings)
    yield


app = FastAPI(title="DocChat API", lifespan=lifespan)

# Added first so CORS (added last, hence outermost) also covers the size-limit error response.
app.add_middleware(UploadSizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str


class UploadResponse(BaseModel):
    id: str
    filename: str
    chunk_count: int


class DeleteResponse(BaseModel):
    id: str
    deleted_chunks: int


class ChatRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    document_ids: list[str] | None = None
    # Recent messages, oldest first; only the last few are used to rewrite follow-ups.
    history: list[generate.HistoryMessage] = []


class ChatResponse(BaseModel):
    answer: str
    sources: list[retrieve.Chunk]
    # The standalone query used for retrieval; null if the question was used as typed.
    rewritten_question: str | None = None


class SourcesEvent(BaseModel):
    type: Literal["sources"] = "sources"
    sources: list[retrieve.Chunk]
    rewritten_question: str | None = None


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    text: str


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


AnyStreamEvent = Annotated[
    SourcesEvent | TokenEvent | DoneEvent | ErrorEvent, Field(discriminator="type")
]


class StreamEvent(RootModel[AnyStreamEvent]):
    """Documents the `data:` payloads of /chat/stream in the OpenAPI schema."""


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/documents", response_model=UploadResponse, status_code=201)
async def upload_document(file: UploadFile) -> UploadResponse:
    filename = PurePath(file.filename or "").name
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, too_large_message())
    try:
        result = await run_in_threadpool(ingest.ingest_document, filename, data)
    except ingest.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    return UploadResponse(
        id=result.document_id,
        filename=filename,
        chunk_count=result.chunk_count,
    )


def _require_documents() -> None:
    if store.count_chunks() == 0:
        raise HTTPException(409, "No documents have been indexed yet. Upload a document first.")


def _retrieve_sources(question: str, document_ids: list[str] | None) -> list[retrieve.Chunk]:
    sources = retrieve.retrieve(question, document_ids=document_ids)
    if not sources:
        raise HTTPException(404, "None of the selected documents were found.")
    return sources


def _rewritten(original: str, standalone: str) -> str | None:
    return standalone if standalone != original else None


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(enforce_chat_rate_limit)])
def chat(request: ChatRequest) -> ChatResponse:
    _require_documents()
    try:
        client = generate.get_client()
        question = generate.rewrite_question(request.question, request.history, client)
        sources = _retrieve_sources(question, request.document_ids)
        answer = generate.answer(question, sources, client)
    except generate.GenerationError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return ChatResponse(
        answer=answer, sources=sources, rewritten_question=_rewritten(request.question, question)
    )


def _sse(event: BaseModel) -> str:
    return f"data: {event.model_dump_json()}\n\n"


async def _stream_events(
    http_request: Request,
    question: str,
    sources: list[retrieve.Chunk],
    client: AsyncAnthropic,
    rewritten_question: str | None = None,
) -> AsyncIterator[str]:
    yield _sse(SourcesEvent(sources=sources, rewritten_question=rewritten_question))
    tokens = generate.stream_answer(question, sources, client)
    try:
        async with aclosing(tokens):
            async for text in tokens:
                if await http_request.is_disconnected():
                    return
                yield _sse(TokenEvent(text=text))
    except generate.GenerationError as exc:
        yield _sse(ErrorEvent(message=str(exc)))
        return
    except Exception:
        # The response has already started, so report the failure as an event, not a 500.
        logger.exception("Unexpected error while streaming an answer")
        yield _sse(ErrorEvent(message="Something went wrong while generating the answer."))
        return
    yield _sse(DoneEvent())


@app.post(
    "/chat/stream",
    response_class=EventStreamResponse,
    responses={200: {"model": StreamEvent, "description": "Server-sent events"}},
    dependencies=[Depends(enforce_chat_rate_limit)],
)
async def chat_stream(request: ChatRequest, http_request: Request) -> EventStreamResponse:
    _require_documents()
    try:
        client = generate.get_async_client()
    except generate.GenerationError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    question = await generate.arewrite_question(request.question, request.history, client)
    sources = await run_in_threadpool(_retrieve_sources, question, request.document_ids)
    return EventStreamResponse(
        _stream_events(
            http_request, question, sources, client, _rewritten(request.question, question)
        ),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/documents", response_model=list[store.DocumentInfo])
def list_documents() -> list[store.DocumentInfo]:
    return store.list_documents()


@app.delete("/documents/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: str) -> DeleteResponse:
    deleted = store.delete_document(document_id)
    if deleted == 0:
        raise HTTPException(404, f"Document '{document_id}' not found.")
    return DeleteResponse(id=document_id, deleted_chunks=deleted)
