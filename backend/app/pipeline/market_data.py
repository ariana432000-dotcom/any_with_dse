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
import logging
import urllib.request
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)

# Watchlist polling can fetch several DSE tickers concurrently (each via
# asyncio.to_thread -> a real OS thread), and every one of them calls
# bdshare -> dsebd.org. urllib3's default connection pool (size 10) can't
# hold that many at once, producing repeated "Connection pool is full,
# discarding connection: dsebd.org" warnings. This throttles our own calls
# so we never have more than a few in flight at once — cheaper and more
# reliable than trying to reconfigure bdshare's internal session, which we
# don't control.
import threading
_DSEBD_CONCURRENCY = threading.Semaphore(3)


def _stooq_symbol(symbol: str, asset_type: str = "stock") -> str:
    s = symbol.strip().lower()
    if asset_type == "crypto":
        # Stooq uses e.g. btc.v / eth.v ; fall back to appending .us otherwise
        return s if "." in s else f"{s}"
    return s if "." in s else f"{s}.us"


def fetch_ohlcv(symbol: str, start: str, end: str, asset_type: str = "stock"):
    """Return a list of dict rows [{date,open,high,low,close,volume}], newest last.

    ✅ CHANGED (DSE): a live DSE trading code routes to bdshare instead of
    yfinance/Stooq, neither of which carry Dhaka Stock Exchange data. Same
    row shape either way, so get_history()/get_quote()/compute_indicators()
    in app/services/market_data.py need no changes to pick this up.

    Tries yfinance first (if installed), then Stooq's keyless CSV endpoint.
    Returns [] on failure rather than raising.
    """
    from tradingagents.dataflows.symbol_utils import is_dse_ticker
    if is_dse_ticker(symbol):
        return _fetch_dse_ohlcv(symbol, start, end)
    rows = _fetch_yfinance(symbol, start, end)
    if rows:
        return rows
    return _fetch_stooq(symbol, start, end, asset_type)


def _fetch_dse_ohlcv(symbol: str, start: str, end: str):
    """DSE OHLCV via bdshare, reshaped to fetch_ohlcv's row contract. Fails
    soft to [] — never raises, matching _fetch_yfinance/_fetch_stooq."""
    try:
        from bdshare import get_historical_data
        with _DSEBD_CONCURRENCY:
            df = get_historical_data(start, end, symbol.upper())
    except Exception:  # noqa: BLE001
        return []
    if df is None or df.empty:
        return []
    df = df.sort_index(ascending=True).reset_index()
    out = []
    for _, r in df.iterrows():
        try:
            out.append({
                "date": str(r["date"])[:10],
                "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": float(r["volume"]) if r.get("volume") not in (None, "") else None,
            })
        except Exception:  # noqa: BLE001
            continue
    return out


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
    """✅ CHANGED (DSE): a live DSE trading code routes to bdshare/
    sharenews24 instead of Google News RSS, which returns nothing
    meaningful for Dhaka-listed tickers. Same {title, source, url} row
    shape either way."""
    from tradingagents.dataflows.symbol_utils import is_dse_ticker
    if is_dse_ticker(symbol):
        return _fetch_dse_news(symbol, limit)

    """Real, keyless headlines via Google News RSS. Fails soft to []."""
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(symbol + ' stock')}&hl=en-US&gl=US&ceid=US:en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            xml = resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return []
    return _parse_rss_titles(xml, limit)


def _fetch_dse_news(symbol: str, limit: int = 8):
    """DSE headlines from every bdshare feed + sharenews24.com.

    bdshare sources (matched by ticker code — reliable, structured, but no
    per-article URL since these are disclosure rows, not articles):
      - get_all_news                general dsebd.org disclosures
      - get_price_sensitive_news    price-sensitive announcements
      - get_corporate_announcements separate announcement feed (criteria=2)
      - get_agm_news                AGM/dividend declarations — has no
                                     per-ticker filter, so this fetches all
                                     companies and filters by name locally

    sharenews24.com (matched by company NAME, not ticker code — headlines
    reference "Square Pharmaceuticals", never "SQURPHARMA", so matching the
    raw ticker here silently never fires). Only attempted for tickers in
    _DSE_COMPANY_NAMES below; these DO carry real clickable article URLs.

    Fails soft — any single source failing just means fewer results, never
    a crash, and never raises.
    """
    out = []
    seen_titles = set()
    sym = symbol.upper()
    dsebd_archive_url = f"https://www.dsebd.org/news_archive.php?symbol={sym}"
    import re
    _sym_pattern = re.compile(rf"\b{re.escape(sym)}\b")
    # Cap per-source so no single bdshare feed (get_corporate_announcements
    # alone can return 400+ rows) crowds out every other source before the
    # link-bearing sites (sharenews24/stocknow/amarstock) get a turn.
    _PER_SOURCE_CAP = 3

    def _add_rows(df, source):
        """✅ CHANGED: get_price_sensitive_news/get_corporate_announcements
        accept a code= filter but DSE's own server ignores it for these two
        categories (confirmed live: ABBANK's feed returned EXCH/EIL/IPDC
        items unrelated to ABBANK) — so every row is re-checked here for an
        actual \\bTICKER\\b match before being kept, regardless of which
        bdshare call it came from. Also dedupes by title text, since price-
        sensitive and corporate turned out to be near-identical unfiltered
        feeds."""
        if df is None or df.empty:
            return 0
        n = 0
        for _, row in df.iterrows():
            if n >= _PER_SOURCE_CAP:
                break
            text = " | ".join(str(v) for v in row.values if str(v).strip())
            if not text or not _sym_pattern.search(text.upper()):
                continue
            if text in seen_titles:
                continue
            seen_titles.add(text)
            trimmed = text if len(text) <= 300 else text[:300].rstrip() + "…"
            out.append({"title": trimmed, "source": source, "url": dsebd_archive_url})
            n += 1
        return n

    try:
        from bdshare import get_all_news
        with _DSEBD_CONCURRENCY:
            df_all = get_all_news(code=sym)
        n = _add_rows(df_all, "dsebd.org")
        _log.info("DSE news[%s] get_all_news: %d rows", sym, n)
    except Exception as e:  # noqa: BLE001
        _log.warning("DSE news[%s] get_all_news failed: %s", sym, e)

    try:
        from bdshare import get_price_sensitive_news
        with _DSEBD_CONCURRENCY:
            df_psn = get_price_sensitive_news(code=sym)
        n = _add_rows(df_psn, "dsebd.org (price-sensitive)")
        _log.info("DSE news[%s] get_price_sensitive_news: %d rows", sym, n)
    except Exception as e:  # noqa: BLE001
        _log.warning("DSE news[%s] get_price_sensitive_news failed: %s", sym, e)

    try:
        from bdshare import get_corporate_announcements
        with _DSEBD_CONCURRENCY:
            df_corp = get_corporate_announcements(code=sym)
        n = _add_rows(df_corp, "dsebd.org (corporate)")
        _log.info("DSE news[%s] get_corporate_announcements: %d rows", sym, n)
    except Exception as e:  # noqa: BLE001
        _log.warning("DSE news[%s] get_corporate_announcements failed: %s", sym, e)

    company_name = _DSE_COMPANY_NAMES.get(sym)
    _log.info("DSE news[%s] company_name lookup: %r", sym, company_name)

    try:
        from bdshare import get_agm_news
        with _DSEBD_CONCURRENCY:
            df = get_agm_news()
        if df is not None and not df.empty and "company" in df.columns:
            needle = (company_name or sym).lower()
            mask = df["company"].astype(str).str.lower().str.contains(needle, na=False)
            n = _add_rows(df[mask], "dsebd.org (AGM/dividend)")
            _log.info("DSE news[%s] get_agm_news: %d/%d rows matched %r", sym, n, len(df), needle)
        else:
            _log.info("DSE news[%s] get_agm_news: empty or no 'company' column", sym)
    except Exception as e:  # noqa: BLE001
        _log.warning("DSE news[%s] get_agm_news failed: %s", sym, e)

    if not company_name:
        _log.info("DSE news[%s] skipping sharenews24 — no company name mapped for this ticker", sym)
    else:
        try:
            req = urllib.request.Request(
                "https://sharenews24.com",
                headers={"User-Agent": "Mozilla/5.0 (compatible; personal-research-bot/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = getattr(resp, "status", "?")
                html = resp.read().decode("utf-8", "replace")
            _log.info("DSE news[%s] sharenews24 fetched: HTTP %s, %d bytes", sym, status, len(html))
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            all_links = soup.find_all("a", href=True)
            matched = 0
            for link in all_links:
                title = link.get_text(strip=True)
                if len(title) < 15 or company_name.lower() not in title.lower():
                    continue
                href = link["href"]
                full_link = href if href.startswith("http") else f"https://sharenews24.com{href}"
                out.append({"title": title, "source": "sharenews24.com", "url": full_link})
                matched += 1
                if matched >= _PER_SOURCE_CAP:
                    break
            _log.info("DSE news[%s] sharenews24: %d/%d links matched %r",
                      sym, matched, len(all_links), company_name)
            if matched == 0 and all_links:
                sample = [l.get_text(strip=True) for l in all_links if len(l.get_text(strip=True)) >= 15][:5]
                _log.info("DSE news[%s] sharenews24 sample headlines (no match found): %r", sym, sample)
        except Exception as e:  # noqa: BLE001
            _log.warning("DSE news[%s] sharenews24 fetch failed: %s", sym, e)

    # stocknow.com.bd — ⚠️ this site's news page is JS-rendered per
    # DSE_VENDOR_README.md's own notes (a discover_stocknow_api.py tool was
    # written to find the underlying data API but never wired in here). A
    # plain requests+BeautifulSoup fetch below may legitimately come back
    # with 0 matches even though the page "looks" like it loaded — the log
    # line distinguishes a real fetch failure from "page loaded, but the
    # actual headlines are injected by JS after load, so the raw HTML we
    # got has no <a> tags with real article text in them."
    if company_name:
        try:
            req = urllib.request.Request(
                "https://www.stocknow.com.bd/news",
                headers={"User-Agent": "Mozilla/5.0 (compatible; personal-research-bot/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = getattr(resp, "status", "?")
                html = resp.read().decode("utf-8", "replace")
            _log.info("DSE news[%s] stocknow.com.bd fetched: HTTP %s, %d bytes", sym, status, len(html))
            if len(html) < 10000:
                _log.info("DSE news[%s] stocknow.com.bd raw HTML sample (page is small — "
                          "checking for JS-shell): %r", sym, html[:600])
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            all_links = soup.find_all("a", href=True)
            matched = 0
            for link in all_links:
                title = link.get_text(strip=True)
                if len(title) < 15 or company_name.lower() not in title.lower():
                    continue
                href = link["href"]
                full_link = href if href.startswith("http") else f"https://www.stocknow.com.bd{href}"
                out.append({"title": title, "source": "stocknow.com.bd", "url": full_link})
                matched += 1
                if matched >= _PER_SOURCE_CAP:
                    break
            _log.info("DSE news[%s] stocknow.com.bd: %d/%d links matched %r (0 total links found "
                      "usually means JS-rendered content — see comment above)",
                      sym, matched, len(all_links), company_name)
        except Exception as e:  # noqa: BLE001
            _log.warning("DSE news[%s] stocknow.com.bd fetch failed: %s", sym, e)

    # amarstock.com/dse-news — same best-effort static-HTML approach as
    # sharenews24; unverified against the live site (not reachable from my
    # sandbox), so the log line is the only way to know if this worked.
    if company_name:
        try:
            req = urllib.request.Request(
                "https://www.amarstock.com/dse-news",
                headers={"User-Agent": "Mozilla/5.0 (compatible; personal-research-bot/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = getattr(resp, "status", "?")
                html = resp.read().decode("utf-8", "replace")
            _log.info("DSE news[%s] amarstock.com fetched: HTTP %s, %d bytes", sym, status, len(html))
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            all_links = soup.find_all("a", href=True)
            matched = 0
            for link in all_links:
                title = link.get_text(strip=True)
                if len(title) < 15 or company_name.lower() not in title.lower():
                    continue
                href = link["href"]
                full_link = href if href.startswith("http") else f"https://www.amarstock.com{href}"
                out.append({"title": title, "source": "amarstock.com", "url": full_link})
                matched += 1
                if matched >= _PER_SOURCE_CAP:
                    break
            _log.info("DSE news[%s] amarstock.com: %d/%d links matched %r",
                      sym, matched, len(all_links), company_name)
            if matched == 0 and all_links:
                sample = [l.get_text(strip=True) for l in all_links if len(l.get_text(strip=True)) >= 15][:5]
                _log.info("DSE news[%s] amarstock.com sample headlines (no match found): %r", sym, sample)
        except Exception as e:  # noqa: BLE001
            _log.warning("DSE news[%s] amarstock.com fetch failed: %s", sym, e)

    # With 7 sources capped at _PER_SOURCE_CAP each, `out` can hold more
    # than `limit` items — trim by preferring linked items first (a
    # clickable article is more useful than a disclosure row pointing at
    # the same generic archive page), then fill any remaining slots with
    # the rest in the order they were collected.
    linked = [item for item in out if item["url"] and "news_archive.php" not in item["url"]]
    rest = [item for item in out if item not in linked]
    return (linked + rest)[:limit]


# Best-effort ticker -> common company name, needed because sharenews24.com
# (and get_agm_news's company-name matching) reference companies by name,
# never by DSE trading code. Not exhaustive — extend as you cover more
# tickers. A ticker missing here still gets full bdshare coverage above
# (those match by code, not name); it just skips the sharenews24 pass and
# falls back to code-matching against get_agm_news's company column, which
# usually won't hit.
_DSE_COMPANY_NAMES = {
    "SQURPHARMA": "Square Pharmaceuticals",
    "GP": "Grameenphone",
    "BEXIMCO": "Beximco",
    "RFL": "RFL",
    "BATBC": "British American Tobacco Bangladesh",
    "ROBI": "Robi Axiata",
    "WALTONHIL": "Walton Hi-Tech",
    "BRACBANK": "BRAC Bank",
    "ISLAMIBANK": "Islami Bank",
    "LHBL": "LafargeHolcim Bangladesh",
}


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
        link_m = re.search(r"<link>(.*?)</link>", it, re.DOTALL)
        url = link_m.group(1).strip() if link_m else None
        out.append({
            "title": title,
            "source": (src.group(1).strip() if src else "News"),
            "url": url,
        })
    return out


import urllib.parse  # noqa: E402  (used by fetch_recent_news)
