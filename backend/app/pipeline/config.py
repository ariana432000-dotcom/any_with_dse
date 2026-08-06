"""
Central configuration for the RAEM Trading Desk.

Everything the pipeline needs to talk to your local setup lives here, and every
value can be overridden with an environment variable so you never have to edit
code to point it at a different machine.

The most important one to get right on first run is TRADINGAGENTS_PATH — the
folder that contains the `tradingagents/` package from the TradingAgents repo.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _env(name: str, default: str) -> str:
    val = os.environ.get(name)
    return val if val is not None and val.strip() != "" else default


# --------------------------------------------------------------------------
# TradingAgents package location
# --------------------------------------------------------------------------
# Point this at the directory that holds the `tradingagents/` package.
# Default matches the path used in the original notebook; override with the
# TRADINGAGENTS_PATH environment variable.
TRADINGAGENTS_PATH = _env("TRADINGAGENTS_PATH", "")


def ensure_tradingagents_on_path() -> bool:
    """Make sure `import tradingagents` works. Returns True if it looks valid.

    This backend already vendors `tradingagents/` directly under the backend
    root (alongside `app/`), so the common case needs no path surgery at all —
    check that first. TRADINGAGENTS_PATH / the legacy fallbacks below only
    matter for a standalone copy of this pipeline pointed at an external
    TradingAgents checkout.
    """
    backend_root = Path(__file__).resolve().parent.parent.parent
    candidates = [str(backend_root), TRADINGAGENTS_PATH]
    here = backend_root
    candidates += [
        str(here / "TradingAgents-main"),
        str(here.parent / "TradingAgents-main"),
        str(here / "TradingAgents"),
    ]
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        if (p / "tradingagents").is_dir():
            if c not in sys.path:
                sys.path.insert(0, c)
            return True
    return False


# --------------------------------------------------------------------------
# Ollama (local LLM + embeddings)
# --------------------------------------------------------------------------
OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_URL = _env("OLLAMA_EMBED_URL", f"{OLLAMA_BASE_URL}/api/embeddings")
LLM_MODEL = _env("RAEM_LLM_MODEL", "qwen2.5:7b")
EMBED_MODEL = _env("RAEM_EMBED_MODEL", "nomic-embed-text")
LLM_TEMPERATURE = float(_env("RAEM_LLM_TEMPERATURE", "0"))

# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
# Where session logs and the Chroma DB live. Defaults to this project folder so
# the desk is self-contained; point at the notebook's folder to share its data.
DATA_DIR = Path(_env("RAEM_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_DB_PATH = _env("RAEM_CHROMA_PATH", str(DATA_DIR / "raem_chroma_db"))
LOG_MAX_DAYS = int(_env("RAEM_LOG_MAX_DAYS", "10"))


def log_file_for(company: str) -> Path:
    """One JSON log per ticker, matching the notebook's naming."""
    safe = "".join(ch for ch in company.upper() if ch.isalnum() or ch in ("-", "_"))
    return DATA_DIR / f"trading_log_{safe}.json"


# --------------------------------------------------------------------------
# Pipeline defaults (overridable per-run from the UI)
# --------------------------------------------------------------------------
DEFAULT_COMPANY = _env("RAEM_DEFAULT_COMPANY", "AAPL")
DEFAULT_ASSET_TYPE = _env("RAEM_DEFAULT_ASSET_TYPE", "stock")
DEFAULT_INVESTMENT_ROUNDS = int(_env("RAEM_INVESTMENT_ROUNDS", "2"))
DEFAULT_RISK_ROUNDS = int(_env("RAEM_RISK_ROUNDS", "3"))
DEFAULT_INVESTOR_PROFILE = _env("RAEM_INVESTOR_PROFILE", "Aggressive")

# Technical indicators the market analyst pulls (matches the notebook)
MARKET_INDICATORS = ["rsi", "macd", "close_50_sma", "boll_ub", "boll_lb"]

# --------------------------------------------------------------------------
# Demo mode
# --------------------------------------------------------------------------
# When DEMO_MODE is on, the pipeline produces realistic simulated output
# WITHOUT contacting Ollama, ChromaDB, or TradingAgents. Use it to preview the
# interface or develop the UI. Real runs need it OFF (the default).
DEMO_MODE = _env("RAEM_DEMO_MODE", "0") in ("1", "true", "True", "yes", "on")


def as_dict() -> dict:
    """Snapshot for display in the UI / health check."""
    return {
        "tradingagents_path": TRADINGAGENTS_PATH,
        "ollama_base_url": OLLAMA_BASE_URL,
        "llm_model": LLM_MODEL,
        "embed_model": EMBED_MODEL,
        "chroma_db_path": CHROMA_DB_PATH,
        "data_dir": str(DATA_DIR),
        "demo_mode": DEMO_MODE,
        "investment_rounds": DEFAULT_INVESTMENT_ROUNDS,
        "risk_rounds": DEFAULT_RISK_ROUNDS,
    }
