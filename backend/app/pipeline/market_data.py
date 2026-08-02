"""
Real market data — keyless, no account required.

Fetches daily OHLCV from Stooq (primary) or yfinance (if installed) and computes
the technical indicators the pipeline uses (RSI, MACD, 50-day SMA, Bollinger
bands). This lets the app pull genuine finance data out of the box, without the
TradingAgents package configured.

Pure-Python indicator math (below) is offline-testable; only the fetch needs the
network, and it fails soft so a run never crashes on a bad symbol.
"""

from __future__ import annotations

import io
import urllib.request
from datetime import datetime, timedelta


def _stooq_symbol(symbol: str, asset_type: str = "stock") -> str:
    s = symbol.strip().lower()
    if asset_type == "crypto":
        # Stooq uses e.g. btc.v / eth.v ; fall back to appending .us otherwise
        return s if "." in s else f"{s}"
    return s if "." in s else f"{s}.us"


def fetch_ohlcv(symbol: str, start: str, end: str, asset_type: str = "stock"):
    """Return a list of dict rows [{date,open,high,low,close,volume}], newest last.

    Tries yfinance first (if installed), then Stooq's keyless CSV endpoint.
    Returns [] on failure rather than raising.
    """
    rows = _fetch_yfinance(symbol, start, end)
    if rows:
        return rows
    return _fetch_stooq(symbol, start, end, asset_type)


def _fetch_yfinance(symbol, start, end):
    try:
        import yfinance as yf  # optional dependency
    except Exception:  # noqa: BLE001
        return []
    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
        if df is None or df.empty:
            return []
        out = []
        for idx, r in df.iterrows():
            def g(col):
                v = r[col]
                try:
                    return float(v.iloc[0]) if hasattr(v, "iloc") else float(v)
                except Exception:  # noqa: BLE001
                    return None
            out.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": g("Open"), "high": g("High"), "low": g("Low"),
                "close": g("Close"), "volume": g("Volume"),
            })
        return [r for r in out if r["close"] is not None]
    except Exception:  # noqa: BLE001
        return []


def _fetch_stooq(symbol, start, end, asset_type):
    s = _stooq_symbol(symbol, asset_type)
    url = (f"https://stooq.com/q/d/l/?s={s}&d1={start.replace('-', '')}"
           f"&d2={end.replace('-', '')}&i=d")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return []
    return parse_stooq_csv(text)


def parse_stooq_csv(text: str):
    """Parse Stooq's 'Date,Open,High,Low,Close,Volume' CSV into row dicts."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2 or not lines[0].lower().startswith("date"):
        return []
    rows = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            rows.append({
                "date": parts[0],
                "open": float(parts[1]), "high": float(parts[2]),
                "low": float(parts[3]), "close": float(parts[4]),
                "volume": float(parts[5]) if len(parts) > 5 and parts[5] not in ("", "N/A") else 0.0,
            })
        except ValueError:
            continue
    return rows


# --------------------------------------------------------------------------
# Indicator math (pure Python — offline testable)
# --------------------------------------------------------------------------
def _sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema_series(values, period):
    if not values:
        return []
    k = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow:
        return None
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    return macd_line[-1]


def _bollinger(closes, period=20, mult=2.0):
    if len(closes) < period:
        return None, None
    window = closes[-period:]
    mid = sum(window) / period
    var = sum((c - mid) ** 2 for c in window) / period
    std = var ** 0.5
    return mid + mult * std, mid - mult * std


def compute_indicators(rows) -> dict:
    """Compute the five indicators the pipeline expects from OHLCV rows."""
    closes = [r["close"] for r in rows if r.get("close") is not None]
    if not closes:
        return {}
    ub, lb = _bollinger(closes)
    ind = {
        "rsi": _rsi(closes),
        "macd": _macd(closes),
        "close_50_sma": _sma(closes, 50) or _sma(closes, min(len(closes), 20)),
        "boll_ub": ub,
        "boll_lb": lb,
    }
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in ind.items() if v is not None}


def to_csv_string(rows, limit: int = 40) -> str:
    """Render rows back to the CSV shape downstream code parses for entry price."""
    head = "Date,Open,High,Low,Close,Volume"
    body = [f"{r['date']},{r['open']},{r['high']},{r['low']},{r['close']},{int(r.get('volume', 0))}"
            for r in rows[-limit:]]
    return "\n".join([head] + body)


def latest_close(rows):
    for r in reversed(rows):
        if r.get("close") is not None:
            return r["close"]
    return None


def window_dates(end_date: str, days_back: int = 220):
    """Give a (start, end) covering enough history to compute a 50-day SMA."""
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start = end - timedelta(days=days_back)
    return start.strftime("%Y-%m-%d"), end_date


def fetch_recent_news(symbol: str, limit: int = 8):
    """Real, keyless headlines via Google News RSS. Fails soft to []."""
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(symbol + ' stock')}&hl=en-US&gl=US&ceid=US:en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            xml = resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return []
    return _parse_rss_titles(xml, limit)


def _parse_rss_titles(xml: str, limit: int):
    import re
    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    out = []
    for it in items[:limit]:
        m = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        if not m:
            continue
        title = m.group(1)
        title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", title).strip()
        src = re.search(r"<source[^>]*>(.*?)</source>", it, re.DOTALL)
        out.append({"title": title, "source": (src.group(1).strip() if src else "News")})
    return out


import urllib.parse  # noqa: E402  (used by fetch_recent_news)
