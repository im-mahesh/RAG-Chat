# Build from the repository root:  docker build -f apps/api/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    CHROMA_PATH=/data/chroma \
    HF_HOME=/data/hf

RUN pip install --no-cache-dir uv==0.13.7

WORKDIR /app

# Dependencies first so this layer is cached until the lockfile changes.
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/.python-version ./
RUN uv sync --frozen --no-dev

COPY apps/api/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
