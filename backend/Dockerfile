FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for building wheels (chromadb/hnswlib, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Chroma persistent dir + scheduled dataset-export CSVs
RUN mkdir -p /data/chroma /data/dataset

EXPOSE 8000

# ✅ CHANGED (Railway): Railway assigns a dynamic $PORT and routes traffic to
# it — a hardcoded --port 8000 would silently break public networking there.
# Shell form (not exec-array form) so $PORT actually expands; falls back to
# 8000 when unset, so `docker compose up` / a plain `docker run` locally are
# unaffected.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/api/v1/health/live || exit 1

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
