# DocChat

A RAG app: users upload documents and chat with them, getting streamed answers with citations.

> Status: scaffolded (API `/health`, web shell with sidebar + chat placeholders, api-client package). No product features yet. Follow the conventions below when adding them.

## Repo layout

pnpm-workspaces monorepo.

```
apps/
  api/             Python 3.12, FastAPI, managed with uv (pyproject.toml, uv.lock)
    app/           the Python package (run as `app.main:app`)
      main.py      FastAPI app, CORS, routes (/health, POST|GET /documents, DELETE /documents/{id}, POST /chat), SSE endpoints
      ingest.py    extract_text, chunk_text, embed, ingest_document (model loaded once at startup)
      retrieve.py  retrieve(question, k, document_ids, settings) -> list[Chunk]: vector search, optional BM25 + RRF (hybrid), optional cross-encoder rerank
      generate.py  answer(question, chunks) via the Anthropic Messages API (non-streaming so far)
      store.py     Chroma persistent client, "docs" collection (cosine), add/delete/list/count helpers
    eval/          retrieval eval harness: docs/ (16 sample docs), questions.json (20 questions), run.py
    tests/         pytest tests; conftest.py fakes `ingest.embed` (keyword vectors), provides FakeAnthropic, and points Chroma at a tmp dir
  web/             React 18 + TypeScript + Vite
    src/api.ts     typed fetch functions (listDocuments, uploadDocument, deleteDocument, chat); types come from `api-client`, never hand-written
    src/store.ts   Zustand: chat messages, selected document filter, mobile sidebar state
    src/hooks/     TanStack Query hooks (useDocuments, useUploadDocuments, useDeleteDocument, useAsk)
    src/upload.ts  client-side file validation (types, 10 MB)
    src/components/  components, each with a colocated *.module.css
scripts/
  setup.sh         one-shot bootstrap for a fresh machine (see Commands)
docker-compose.yml runs api + web; apps/api/Dockerfile, apps/web/Dockerfile (+ nginx.conf), .dockerignore
.github/workflows/ci.yml   backend tests; frontend type-check, lint, tests
README.md          user-facing docs (diagrams, setup, env vars); keep it in sync with the env var table below
docs/              README assets (screenshot placeholder)
packages/
  api-client/      TS types generated from FastAPI's OpenAPI schema (do not hand-edit)
data/              local runtime data, gitignored (Chroma lives in data/chroma)
```

Backend logic lives in the five modules above. Do not add new top-level modules without asking.

## Stack

### Backend (`apps/api`)
- FastAPI, Python 3.12, dependencies managed with `uv`.
- Vector store: Chroma, persistent, stored in `./data/chroma`.
- Embeddings: `sentence-transformers` with `all-MiniLM-L6-v2`.
- Generation: Anthropic Python SDK, model `claude-sonnet-5-5`.
- `ANTHROPIC_API_KEY` is read from the environment, loaded from `.env`. Never commit `.env`.
- Type hints on every function signature. Pydantic models for all request/response bodies and for data passed between modules.

### Frontend (`apps/web`)
- React 18 + TypeScript + Vite.
- Server state: TanStack Query. UI state: Zustand. Don't mix them (no server data in Zustand).
- Styling: plain CSS modules. No UI library, no CSS-in-JS, no Tailwind.
- Streaming: `fetch` + `ReadableStream` to consume SSE. No EventSource, no SSE library.

### API client (`packages/api-client`)
- Types are generated from the FastAPI OpenAPI schema. Change the backend models, then regenerate; never edit generated files by hand.

## Commands

Run from the repo root unless noted.

| Task | Command |
| --- | --- |
| Run in Docker | `docker compose up --build` (web on :5173, api on :8000, `./data` mounted at `/data`; needs `ANTHROPIC_API_KEY` in `.env` or the shell) |
| Web type-check | `pnpm --filter web typecheck` |
| Fresh machine setup | `bash scripts/setup.sh` (installs uv, Node, pnpm, all deps, `.env`, embedding model; re-runnable; `--skip-model`, `--no-profile`) |
| Install deps only | `pnpm install` and `cd apps/api && uv sync` |
| Run API (port 8000) | `pnpm dev:api` |
| Run web (port 5173) | `pnpm dev:web` |
| Run both | `pnpm dev` |
| Regenerate API types | `pnpm gen:types` (the API must be running on :8000) |
| Backend tests | `cd apps/api && uv run pytest` |
| Retrieval eval | `cd apps/api && uv run python -m eval.run [--modes ...] [--k 5] [--verbose]` |
| Web typecheck + build | `pnpm --filter web build` |
| Web lint | `pnpm --filter web lint` |
| Web tests | `pnpm --filter web test` |

Web tests use Vitest + React Testing Library (jsdom): `pnpm --filter web test`. Test files sit next to the code (`*.test.ts(x)`); `src/test/setup.ts` registers RTL cleanup (no Vitest globals, no jest-dom: use plain assertions).

Setup: copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.

Gotchas:
- `api-client` pins `typescript@5` because openapi-typescript doesn't work with TypeScript 7 (which `apps/web` uses). Don't unify them.
- The API's CORS allows only `http://localhost:5173`, and Vite uses `strictPort`, so the web app won't silently move to another port.
- `VITE_API_URL` overrides the API base URL in the web app (default `http://localhost:8000`).

## Ingestion notes

- Uploads: pdf/md/txt only, max 10 MB; violations return 400 with a readable `detail`. `IngestError` (a `ValueError`) is the "safe to show the user" error.
- Chunk metadata: `document_id`, `filename`, `chunk_index`, `uploaded_at` (ISO, UTC), plus `page` and `heading` only when present (Chroma rejects `None` metadata). Chunk ids are `{document_id}:{chunk_index}`.
- `CHROMA_PATH` overrides the Chroma directory (default `<repo>/data/chroma`, independent of the cwd). Tests use it.
- The embedding model downloads from Hugging Face on first server start (~90 MB), then is cached. Tests never load it.

## Operations and hardening notes

- Rate limiting: `RateLimiter` (in `main.py`, no extra dependency) is a per-client sliding window on `/chat` and `/chat/stream` (shared budget), `RATE_LIMIT_PER_MINUTE` (default 20, `0` = off). It returns 429 + `Retry-After`. It is in-process, keyed on `request.client.host`, and ignores `X-Forwarded-For`. Tests reset it with an autouse fixture in `conftest.py`; any new test that fires many chat requests relies on that.
- Upload checks, in order: `UploadSizeLimitMiddleware` rejects by `Content-Length` before the body is read (plain ASGI, registered before CORS so the error still carries CORS headers); the endpoint re-checks the real size; then `ingest.py` checks the extension, the `%PDF-` header, and NUL bytes in `.md`/`.txt`. All are 400 with a readable `detail`. pypdf failures of any exception type become `IngestError`, never a 500.
- Unexpected errors after a stream has started become an `error` event with a generic message (details are logged, not sent).
- `CORS_ORIGINS` (comma-separated, default `http://localhost:5173`) controls allowed origins; the Docker web image bakes `VITE_API_URL` in at build time.
- Docker: Dockerfiles are built from the repo root (`context: .`). The api image sets `CHROMA_PATH=/data/chroma` and `HF_HOME=/data/hf`, so documents and downloaded models persist in `./data`. The Docker and CI files were validated statically only (no Docker daemon was available when they were written): run `docker compose up --build` once before relying on them.
- CI (`.github/workflows/ci.yml`) uses major-version tags for actions (not SHA pins) and installs the full locked Python environment, including torch.
- When testing a locally started server from a script, pass settings with `env VAR=... command`; setting them as a prefix to a backgrounded `nohup` once silently dropped them and the test hit the real `data/chroma`.

## Retrieval notes

- Settings (env, read per request; invalid values fail at startup): `RETRIEVAL_MODE=vector|hybrid` (default **hybrid**), `RERANK=true|false` (default **false**), `RETRIEVAL_CANDIDATES` (default 20). The code defaults live at the top of `retrieve.py`.
- Hybrid = vector search + BM25 (`rank_bm25`, whitespace/word tokens, no stemming) over every stored chunk, merged with Reciprocal Rank Fusion (k=60). The BM25 index is cached per (Chroma path, `store.revision()`) and rebuilt after any upload/delete, so keep adding/removing chunks through `store.add_chunks`/`store.delete_document`.
- Rerank = top `RETRIEVAL_CANDIDATES` (20) re-scored by `cross-encoder/ms-marco-MiniLM-L-6-v2`, cut to k (5). The model (~90 MB) is loaded at startup only if `RERANK=true`.
- `Chunk.score` is always the cosine similarity between the question and the chunk, whatever the mode, so it can disagree with the ranking order in hybrid/rerank modes. `Chunk` now also carries `document_id`.
- Query rewriting: `/chat` and `/chat/stream` take `history` (the last 4 messages; the web app sends them, the server also truncates to 4). With history, `generate.rewrite_question` makes one quick `claude-haiku-5-5` call that turns the follow-up into a standalone query; retrieval AND the answer prompt use the rewritten question, and the response/`sources` event carries `rewritten_question` (null if unchanged). A failed rewrite silently falls back to the original question. No history = no extra call.
- Tests never load real models: `conftest.py` pins `RETRIEVAL_MODE=vector`, `RERANK=false` for every test, and fakes the embedder, reranker and Anthropic clients.

### Eval results (`uv run python -m eval.run`, 123 chunks, 20 questions, k=5)

| mode | hit@1 | hit@5 | MRR@5 | ms/query |
| --- | --- | --- | --- | --- |
| vector | 0.75 | 1.00 | 0.875 | 5 |
| hybrid | 0.85 | 1.00 | 0.925 | 4 |
| vector+rerank | 0.85 | 1.00 | 0.925 | 35 |
| hybrid+rerank | 0.85 | 1.00 | 0.925 | 35 |

Read these with care: hit@5 is saturated, and the gaps are 2 questions out of 20 (health-insurance and encryption questions that hybrid and the reranker both fix). Three more questions (Pro rate limit, webhook retries, idempotency window) rank the reference doc 2nd in every mode because the changelog doc legitimately repeats the same facts: that is label ambiguity, equal across modes. A first, easier 8-doc/60-chunk version of the eval scored vector 1.00 on everything, so the corpus was made harder once (more overlapping docs, reworded questions) before comparing modes. Re-run the eval after changing chunking, models or the corpus, and don't tune questions to favour a mode.

## Chat notes

- `POST /chat` `{question, document_ids?}` -> `{answer, sources}`. Empty/omitted `document_ids` searches everything. Sources are numbered `[1]`.. in retrieval order and the model cites those numbers.
- Errors: 409 no documents indexed, 404 none of `document_ids` exist, 503 `ANTHROPIC_API_KEY` missing (or Anthropic unreachable), 429 Anthropic rate limit, 504 timeout, 502 other Anthropic failures/refusals. `GenerationError` carries the status code.
- Generation uses `claude-sonnet-5-5`, `max_tokens=1024`, `output_config.effort="low"` (thinking tokens count toward `max_tokens`, so keep effort low). Don't send `temperature`/`top_p`/`top_k` on this model; they are rejected.
- `POST /chat/stream` (same body) returns `text/event-stream`; each `data:` is JSON: `{"type":"sources","sources":[...]}` first, then `{"type":"token","text":...}` per delta, then `{"type":"done"}`, or `{"type":"error","message":...}` on failure (no `done` after an error). The event models (`StreamEvent`) are in the OpenAPI schema, so the web app gets its types from `api-client`.
- Streaming errors: failures before streaming starts (409, 404, 422, 503 missing key) are plain HTTP errors; anything after the response begins (rate limit, refusal, empty answer, dropped upstream) is an `error` event. The UI handles both.
- Streaming uses `AsyncAnthropic` (`generate.stream_answer`) and checks `request.is_disconnected()` between tokens; leaving the generator closes the Anthropic stream, which stops generation. Tests use `FakeAsyncAnthropic`/`FakeStream` from `conftest.py`.
- There is no minimum-score cutoff on retrieval; irrelevant questions still return top-k (scores near 0) and rely on the prompt's "I don't know" rule.

## Web UI notes

- Sidebar: multi-file upload (drag-and-drop or button, files validated client-side then uploaded one at a time), document list with checkboxes (selected ids restrict `/chat`; none selected = search all) and a delete button. The selection is pruned when documents disappear. Delete has no confirmation.
- Chat streams from `/chat/stream` via `fetch` + `ReadableStream` (`src/sse.ts` is the incremental SSE parser; `streamChat` in `src/api.ts`; `useAsk` drives it). The assistant message fills in token by token with a blinking cursor; the Send button becomes Stop (AbortController); stopped answers keep their partial text with a "Stopped." note; errors appear as a separate red message (an empty assistant bubble is removed). The list only auto-scrolls if the user is near the bottom. The UI only uses `/chat/stream`; the non-streaming `/chat` endpoint is kept for scripts and tests.
- `sse.test.ts` covers the parser: every split point, byte-at-a-time delivery, CRLF and multi-event chunks.
- Chat: Enter sends, Shift+Enter adds a newline, input is disabled while streaming and when there are no documents. Answers render as plain text (`white-space: pre-wrap`); there is no markdown renderer (adding one needs a new dependency, so ask first). Sources are shown under each answer in a `<details>`.
- Citations: assistant text is rendered with `react-markdown` (`MarkdownContent`). `[n]` markers become clickable badges via a remark plugin (`remarkCitations.ts`, built on `parseCitations` in `citations.ts`) that works on the parsed tree, so `[n]` inside code spans, code blocks and link labels stays literal. A number with no matching source (`[7]` with 3 sources) is plain text. Grouped `[1, 2]` becomes two badges. Images in answers are dropped (untrusted text could leak data through an image URL) and links open in a new tab. No `remark-gfm`, so tables/strikethrough aren't rendered; ask before adding it.
- Clicking a badge sets `activeCitation` in the Zustand store and opens `SourcePanel`: all sources of that answer, the clicked one expanded and highlighted, the others collapsed (click to switch). It is a third grid column above 1100px and an overlay (modal) at or below it; Escape closes it and focus returns to the badge. Each answer also has a collapsed "Sources (N)" `<details>` list using the same `SourceCard`.
- Component split: `MessageList` (scroll) -> `MessageBubble` -> `MarkdownContent` / `Sources`; `CitationBadge`, `SourceCard`, `SourcePanel` are standalone.
- Below 768px the sidebar becomes a slide-over drawer (state in the Zustand store).
- `.env.example` leaves `ANTHROPIC_API_KEY=` empty on purpose: an empty value counts as unset, so the API returns the clear 503 instead of sending a fake key to Anthropic.
- Browser automation tip: the built-in browser's `Return` key name doesn't trigger the app's Enter handler; use `Enter`.

## Conventions and rules

- **Commits:** small and focused, one logical change each.
- **Secrets:** none in git. Keys go in `.env` (gitignored); document new variables in `.env.example` with placeholder values only.
- **Tests:** write pytest tests for backend logic (chunking, retrieval, prompt/citation building, store operations). Mock the Anthropic API and avoid network calls in tests.
- **Functions:** keep them short and single-purpose; split when a function does more than one thing.
- **Dependencies:** ask before adding any dependency beyond those listed in this file.
- **Generated code:** `packages/api-client` output is generated; regenerate, don't edit.
- **Data:** `data/` is runtime state and stays out of git.
