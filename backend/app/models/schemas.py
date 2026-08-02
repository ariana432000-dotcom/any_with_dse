"""Pydantic request/response schemas (API contracts)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ---- health ----
class Health(BaseModel):
    status: str
    services: dict[str, Any]
    ai_configured: bool
    ai_provider: str
    ai_model: str
