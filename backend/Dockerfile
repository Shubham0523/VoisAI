# One image, two roles (see start.sh):
#   SERVICE=api    FastAPI on $PORT            (Render web service)
#   default        LiveKit voice agent worker  (LiveKit Cloud agent hosting, or any VM)
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed

# onnxruntime (VAD, turn detector, embeddings) needs OpenMP
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so code changes don't reinstall them
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Bake models into the image: no downloads at call time, no cold-start surprises
RUN python -m voisai.agent.worker download-files \
    && python -c "from voisai.memory.store import _embedder; _embedder()"

RUN chmod +x start.sh
EXPOSE 8000
CMD ["./start.sh"]
