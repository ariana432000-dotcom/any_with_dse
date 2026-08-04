"""
Central configuration for the AInvest platform backend.

Every value is environment-driven (12-factor). Sensible defaults let the stack
boot with `docker compose up` using only keyless providers (Yahoo Finance,
local ChromaDB). Cloud providers (Finnhub, OpenAI, Anthropic, ...) activate the
moment their keys are present in the environment / .env file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ---- app ----
    ENV: Literal["dev", "prod", "test"] = "dev"
    APP_NAME: str = "AInvest Platform"
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )
    LOG_LEVEL: str = "INFO"

    # ---- MongoDB (market history, AI reasoning, news, conversations, watchlists) ----
    MONGO_URI: str = "mongodb://mongo:27017"
    MONGO_DB: str = "ainvest"

    # ---- Redis (cache, task queue, websocket state) ----
    REDIS_URL: str = "redis://redis:6379/0"

    # ---- background execution: off unless a celery_worker is actually deployed ----
    #Ari
    CELERY_ENABLED: bool = False
    
    # ---- ChromaDB (RAEM episodic memory + news RAG, from the notebook) ----
    CHROMA_DB_PATH: str = "/data/chroma"

    # ---- embeddings (provider selected here; no provider code in business logic) ----
    EMBEDDING_PROVIDER: str = "ollama"   # ollama | openai | sentence-transformers
    EMBEDDING_MODEL_OPENAI: str = "text-embedding-3-small"
    EMBEDDING_MODEL_ST: str = "all-MiniLM-L6-v2"

    # ---- embeddings for ChromaDB (genuinely read by ai_engine/memory/embeddings.py) ----
    EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENAI_API_KEY: str = ""   # only used if EMBEDDING_PROVIDER=openai

    # ---- market-data providers (Yahoo keyless default; rest pluggable) ----
    DEFAULT_MARKET_PROVIDER: str = "yahoo"
    FINNHUB_API_KEY: str = ""
    POLYGON_API_KEY: str = ""
    ALPHAVANTAGE_API_KEY: str = ""
    TWELVEDATA_API_KEY: str = ""
    FMP_API_KEY: str = ""
    FRED_API_KEY: str = ""
    NEWSAPI_KEY: str = ""

    # ---- worker cadence ----
    WORKER_INTERVAL_SECONDS: int = 300          # market-data refresh loop
    DEFAULT_WATCH_TICKERS: str = "AAPL,MSFT,NVDA,TSLA,AMZN,BEXIMCO,SQURPHARMA,GP,RANFOUNDRY,AMCL(PRAN)"

    # ---- daily/periodic dataset export (full analysis + decision -> CSV) ----
    # Runs inside the `worker` container's existing scheduler loop (no separate
    # service needed). Every tick it checks whether >= DATASET_JOB_INTERVAL_SECONDS
    # has elapsed since the last run AND (if MARKET_HOURS_ONLY) the market is
    # currently open; if so it runs one full analysis per watchlist ticker and
    # appends a row to that ticker's CSV under DATASET_CSV_PATH.
    DATASET_CSV_PATH: str = "/data/dataset"
    DATASET_JOB_INTERVAL_SECONDS: int = 7200          # every 2 hours
    DATASET_JOB_MARKET_HOURS_ONLY: bool = True         # gate to 9:30-16:00 America/New_York, Mon-Fri
    DATASET_JOB_PER_TICKER_TIMEOUT_SECONDS: int = 1800  # 30 min hard cap per ticker

    # ---- helpers ----
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def watch_tickers(self) -> list[str]:
        return [t.strip().upper() for t in self.DEFAULT_WATCH_TICKERS.split(",") if t.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
