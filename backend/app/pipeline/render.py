"""Render agent markdown into safe HTML for the dashboard."""

from __future__ import annotations

import re

try:
    import markdown as _md
    _MD = _md.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
except Exception:  # noqa: BLE001
    _MD = None


def md_to_html(text: str) -> str:
    if not text:
        return ""
    text = str(text)
    if _MD is not None:
        _MD.reset()
        return _MD.convert(text)
    # Minimal fallback if the markdown package isn't installed.
    return "<p>" + text.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


def first_signal(text: str) -> str:
    if not text:
        return "N/A"
    m = re.search(r"\*{0,2}(BUY|HOLD|SELL)\*{0,2}", str(text), re.IGNORECASE)
    return m.group(1).upper() if m else "N/A"
