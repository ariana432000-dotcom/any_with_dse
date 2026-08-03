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
import re
import time as _time
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


_BDSHARE_DIAG_LOGGED = False


def _log_bdshare_news_functions_once() -> None:
    """Logs, once per process, which of the 4 bdshare news functions this
    file relies on are actually present in the installed bdshare version --
    so a Railway log immediately shows "bdshare 1.x has get_all_news but NOT
    get_agm_news" instead of leaving that to be inferred from 4 separate
    per-request ImportError lines."""
    global _BDSHARE_DIAG_LOGGED
    if _BDSHARE_DIAG_LOGGED:
        return
    _BDSHARE_DIAG_LOGGED = True
    try:
        import bdshare
        version = getattr(bdshare, "__version__", "unknown")
        wanted = ["get_all_news", "get_price_sensitive_news", "get_corporate_announcements", "get_agm_news"]
        present = {name: hasattr(bdshare, name) for name in wanted}
        _log.info("bdshare version=%s, news functions available: %s", version, present)
    except Exception as e:  # noqa: BLE001
        _log.warning("Could not introspect bdshare for diagnostics: %s", e)


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
    seen_titles = set()
    sym = symbol.upper()
    # urllib.parse.quote, not an f-string interpolation — some real DSE
    # tickers contain parentheses (e.g. AMCL(PRAN)), which break Markdown
    # link syntax if dropped into a URL unescaped.
    # ✅ CHANGED: news_archive.php?symbol= was the wrong page — confirmed
    # against the live site. bdshare's own DSE_NEWS_URL constant (what
    # get_all_news/get_price_sensitive_news/get_corporate_announcements
    # actually fetch under the hood) is old_news.php with inst/criteria/
    # archive params — this now points users at the same page our own
    # data is sourced from.
    dsebd_archive_url = (
        f"https://www.dsebd.org/old_news.php"
        f"?inst={urllib.parse.quote(sym)}&criteria=3&archive=news"
    )
    import re
    _sym_pattern = re.compile(rf"\b{re.escape(sym)}\b")

    # ✅ CHANGED: capped and grouped per *website*, not per bdshare feed.
    # dsebd.org alone has 4 sub-feeds (get_all_news, price-sensitive,
    # corporate, AGM) that could each contribute PER_WEBSITE_CAP items —
    # left uncapped as a group, dsebd.org alone could fill the entire
    # `limit` before sharenews24/stocknow/amarstock ever got a turn. Now
    # all 4 dsebd sub-feeds share one bucket capped at PER_WEBSITE_CAP
    # total, same as each of the other 3 sites — so with the default
    # limit=12 you get up to 3 items from each of the 4 websites, evenly.
    PER_WEBSITE_CAP = 3
    groups: dict[str, list[dict]] = {
        "dsebd.org": [],
        "sharenews24.com": [],
        "stocknow.com.bd": [],
        "amarstock.com": [],
    }

    def _add_rows(df, source_label, group="dsebd.org"):
        """✅ CHANGED: get_price_sensitive_news/get_corporate_announcements
        accept a code= filter but DSE's own server ignores it for these two
        categories (confirmed live: ABBANK's feed returned EXCH/EIL/IPDC
        items unrelated to ABBANK) — so every row is re-checked here for an
        actual \\bTICKER\\b match before being kept, regardless of which
        bdshare call it came from. Also dedupes by title text, since price-
        sensitive and corporate turned out to be near-identical unfiltered
        feeds. `group` buckets all 4 dsebd sub-feeds into one shared,
        capped list (see PER_WEBSITE_CAP note above)."""
        bucket = groups[group]
        if df is None or df.empty:
            return 0
        n = 0
        for _, row in df.iterrows():
            if len(bucket) >= PER_WEBSITE_CAP:
                break
            text = " | ".join(str(v) for v in row.values if str(v).strip())
            if not text or not _sym_pattern.search(text.upper()):
                continue
            if text in seen_titles:
                continue
            seen_titles.add(text)
            trimmed = text if len(text) <= 300 else text[:300].rstrip() + "…"
            bucket.append({"title": trimmed, "source": source_label, "url": dsebd_archive_url})
            n += 1
        return n

    # ✅ CHANGED: sharenews24/stocknow/amarstock were matching headlines
    # against the FULL fallback company name only (e.g. "Square
    # Pharmaceuticals") -- these sites commonly use a shorter form ("Square
    # Pharma") or drop the corporate suffix ("... Ltd"/"... PLC"), so an
    # exact full-name substring check silently returns 0 matches even when
    # the site has real coverage. This builds a small set of looser variants
    # (full name, name minus a trailing corporate suffix, first two words,
    # first word) and matches against any of them instead of just the one
    # exact string.
    def _company_name_variants(name: str) -> list[str]:
        name = (name or "").strip()
        if not name:
            return []
        variants = {name}
        lname = name.lower()
        for suffix in (" plc", " limited", " ltd", " ltd.", " co.", " company", " inc"):
            if lname.endswith(suffix):
                variants.add(name[: -len(suffix)].strip())
        words = [w for w in re.split(r"\s+", name) if w.lower() != "the"]
        if len(words) >= 2:
            variants.add(" ".join(words[:2]))
        if words:
            variants.add(words[0])
        # Keep the original full name regardless of length; drop derived
        # variants under 4 chars (too generic, risks matching unrelated
        # headlines).
        return [v for v in variants if v == name or len(v) >= 4]

    def _title_matches_company(title: str, variants: list[str]) -> bool:
        t = title.lower()
        return any(v.lower() in t for v in variants)

    _log_bdshare_news_functions_once()

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
    except ImportError as e:
        _log.warning("DSE news[%s] bdshare has no get_price_sensitive_news in this installed "
                      "version (%s) — not a network issue, check `pip show bdshare`.", sym, e)
    except Exception as e:  # noqa: BLE001
        _log.warning("DSE news[%s] get_price_sensitive_news failed: %s", sym, e)

    try:
        from bdshare import get_corporate_announcements
        with _DSEBD_CONCURRENCY:
            df_corp = get_corporate_announcements(code=sym)
        n = _add_rows(df_corp, "dsebd.org (corporate)")
        _log.info("DSE news[%s] get_corporate_announcements: %d rows", sym, n)
    except ImportError as e:
        _log.warning("DSE news[%s] bdshare has no get_corporate_announcements in this installed "
                      "version (%s) — not a network issue, check `pip show bdshare`.", sym, e)
    except Exception as e:  # noqa: BLE001
        _log.warning("DSE news[%s] get_corporate_announcements failed: %s", sym, e)

    company_name = _load_dse_company_names().get(sym)
    _log.info("DSE news[%s] company_name lookup: %r", sym, company_name)
    # ✅ CHANGED: combine English variants with any known Bengali forms for
    # this ticker (see _DSE_COMPANY_NAMES_BENGALI_FALLBACK note above) --
    # sharenews24.com/amarstock.com write almost exclusively in Bengali, so
    # the English-only variant list never matched their real headlines.
    all_name_variants = (
        _company_name_variants(company_name) + _DSE_COMPANY_NAMES_BENGALI_FALLBACK.get(sym, [])
        if company_name else []
    )

    try:
        from bdshare import get_agm_news
        with _DSEBD_CONCURRENCY:
            df = get_agm_news()
        if df is not None and not df.empty and "company" in df.columns:
            needle = (company_name or sym).lower()
            mask = df["company"].astype(str).str.lower().str.contains(needle, regex=False, na=False)
            n = _add_rows(df[mask], "dsebd.org (AGM/dividend)")
            _log.info("DSE news[%s] get_agm_news: %d/%d rows matched %r", sym, n, len(df), needle)
        else:
            _log.info("DSE news[%s] get_agm_news: empty or no 'company' column", sym)
    except ImportError as e:
        _log.warning("DSE news[%s] bdshare has no get_agm_news in this installed "
                      "version (%s) — not a network issue, check `pip show bdshare`.", sym, e)
    except Exception as e:  # noqa: BLE001
        _log.warning("DSE news[%s] get_agm_news failed: %s", sym, e)

    if not company_name:
        _log.info("DSE news[%s] skipping sharenews24 — no company name mapped for this ticker", sym)
    else:
        # ✅ CHANGED: the homepage mixes in politics/sports/entertainment
        # (sharenews24 is a general newspaper, not stock-only), which
        # drowns out company headlines and wastes most of the PER_WEBSITE_CAP
        # matches on irrelevant links. Confirmed live (2026-08-02 fetch) that
        # sharenews24.com has two dedicated category pages that are all but
        # guaranteed to be stock-market content: শেয়ারবাজার (group/1) and
        # প্রাইস সেনসেটিভ (group/17, price-sensitive disclosures — the exact
        # kind of company-tagged headline dsebd.org itself carries, e.g.
        # "আল-আরাফাহ্ ইসলামী ব্যাংকের দ্বিতীয় প্রান্তিক প্রকাশ"). Both are
        # plain server-rendered HTML, same as the homepage — no JS needed.
        sharenews24_pages = [
            ("শেয়ারবাজার", "https://sharenews24.com/group/1/index.html"),
            ("প্রাইস সেনসেটিভ", "https://sharenews24.com/group/17/index.html"),
        ]
        bucket = groups["sharenews24.com"]
        variants = all_name_variants
        matched_total = 0
        links_seen_total = 0
        no_match_samples: list[str] = []
        for page_name, page_url in sharenews24_pages:
            if matched_total >= PER_WEBSITE_CAP:
                break
            try:
                req = urllib.request.Request(
                    page_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; personal-research-bot/1.0)"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = getattr(resp, "status", "?")
                    html = resp.read().decode("utf-8", "replace")
                _log.info("DSE news[%s] sharenews24[%s] fetched: HTTP %s, %d bytes", sym, page_name, status, len(html))
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                all_links = soup.find_all("a", href=True)
                links_seen_total += len(all_links)
                page_matched = 0
                for link in all_links:
                    if matched_total >= PER_WEBSITE_CAP:
                        break
                    title = link.get_text(strip=True)
                    if len(title) < 15:
                        continue
                    if not _title_matches_company(title, variants):
                        if len(no_match_samples) < 15:
                            no_match_samples.append(title)
                        continue
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)
                    href = link["href"]
                    full_link = href if href.startswith("http") else f"https://sharenews24.com{href}"
                    bucket.append({"title": title, "source": "sharenews24.com", "url": full_link})
                    matched_total += 1
                    page_matched += 1
                _log.info("DSE news[%s] sharenews24[%s]: %d/%d links matched", sym, page_name, page_matched, len(all_links))
            except Exception as e:  # noqa: BLE001
                _log.warning("DSE news[%s] sharenews24[%s] fetch failed: %s", sym, page_name, e)
        _log.info("DSE news[%s] sharenews24 total: %d/%d links matched %r (variants tried: %r)",
                  sym, matched_total, links_seen_total, company_name, variants)
        if matched_total == 0 and no_match_samples:
            _log.info("DSE news[%s] sharenews24 sample headlines (no match found): %r", sym, no_match_samples)

    # stocknow.com.bd — ✅ CHANGED: www.stocknow.com.bd/news is a JS SPA
    # (confirmed live: a plain fetch returns an empty React shell with no
    # article HTML at all — this is *why* this vendor always returned 0
    # matches before, not a transient fetch issue). StockNow's actual
    # editorial coverage lives on a SEPARATE subdomain, news.stocknow.com.bd
    # — plain server-rendered HTML (confirmed live, no JS needed), with real
    # <a href> article links whose slugs often already carry the company
    # name (e.g. "national-credit-and-commerce-bank-limited-2"). Pointing
    # the fetch at the right host is the actual fix here — discover_stocknow_api.py's
    # Playwright route was solving a problem this subdomain doesn't have.
    if company_name:
        stocknow_pages = [
            ("home", "https://news.stocknow.com.bd/"),
            # কোম্পানি সংবাদ (company news) category — broader net than the
            # homepage alone, since the homepage only shows ~15 most recent
            # posts across ALL categories (national/international/sports too).
            ("কোম্পানি সংবাদ", "https://news.stocknow.com.bd/category/%e0%a6%95%e0%a7%8b%e0%a6%ae%e0%a7%8d%e0%a6%aa%e0%a6%be%e0%a6%a8%e0%a6%bf-%e0%a6%b8%e0%a6%82%e0%a6%ac%e0%a6%be%e0%a6%a6/"),
        ]
        bucket = groups["stocknow.com.bd"]
        variants = all_name_variants
        matched_total = 0
        links_seen_total = 0
        for page_name, page_url in stocknow_pages:
            if matched_total >= PER_WEBSITE_CAP:
                break
            try:
                req = urllib.request.Request(
                    page_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; personal-research-bot/1.0)"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = getattr(resp, "status", "?")
                    html = resp.read().decode("utf-8", "replace")
                _log.info("DSE news[%s] news.stocknow.com.bd[%s] fetched: HTTP %s, %d bytes", sym, page_name, status, len(html))
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                all_links = soup.find_all("a", href=True)
                links_seen_total += len(all_links)
                page_matched = 0
                for link in all_links:
                    if matched_total >= PER_WEBSITE_CAP:
                        break
                    title = link.get_text(strip=True)
                    if len(title) < 15 or not _title_matches_company(title, variants):
                        continue
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)
                    href = link["href"]
                    full_link = href if href.startswith("http") else f"https://news.stocknow.com.bd{href}"
                    bucket.append({"title": title, "source": "stocknow.com.bd", "url": full_link})
                    matched_total += 1
                    page_matched += 1
                _log.info("DSE news[%s] news.stocknow.com.bd[%s]: %d/%d links matched", sym, page_name, page_matched, len(all_links))
            except Exception as e:  # noqa: BLE001
                _log.warning("DSE news[%s] news.stocknow.com.bd[%s] fetch failed: %s", sym, page_name, e)
        _log.info("DSE news[%s] stocknow.com.bd total: %d/%d links matched %r", sym, matched_total, links_seen_total, company_name)

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
            bucket = groups["amarstock.com"]
            variants = all_name_variants
            for link in all_links:
                title = link.get_text(strip=True)
                if len(title) < 15 or not _title_matches_company(title, variants):
                    continue
                href = link["href"]
                full_link = href if href.startswith("http") else f"https://www.amarstock.com{href}"
                bucket.append({"title": title, "source": "amarstock.com", "url": full_link})
                matched += 1
                if matched >= PER_WEBSITE_CAP:
                    break
            # ✅ CHANGED: confirmed live (Railway log) that amarstock.com's
            # <a href> links are all nav-menu chrome ("Online Training",
            # "Compare Sector PE", ...) -- the real news text isn't inside
            # anchor tags at all. Fall back to scanning ALL page text lines
            # (not just links) when the anchor pass found nothing; matched
            # lines get the page URL itself as their link (no per-article
            # URL exists for a plain-text hit, same convention as the dsebd
            # disclosure rows above).
            if matched == 0:
                page_text = soup.get_text("\n")
                for line in page_text.splitlines():
                    line = line.strip()
                    if len(line) < 15 or not _title_matches_company(line, variants):
                        continue
                    if line in seen_titles:
                        continue
                    seen_titles.add(line)
                    trimmed = line if len(line) <= 300 else line[:300].rstrip() + "…"
                    bucket.append({"title": trimmed, "source": "amarstock.com", "url": "https://www.amarstock.com/dse-news"})
                    matched += 1
                    if matched >= PER_WEBSITE_CAP:
                        break
                _log.info("DSE news[%s] amarstock.com: text-line fallback found %d matches "
                          "(anchor-tag pass found 0)", sym, matched)
            _log.info("DSE news[%s] amarstock.com: %d/%d links matched %r (variants tried: %r)",
                      sym, matched, len(all_links), company_name, variants)
            if matched == 0 and all_links:
                qualifying = [l.get_text(strip=True) for l in all_links if len(l.get_text(strip=True)) >= 15]
                step = max(1, len(qualifying) // 15)
                sample = qualifying[::step][:15]
                _log.info("DSE news[%s] amarstock.com sample headlines (spread across page, no match found): %r", sym, sample)
        except Exception as e:  # noqa: BLE001
            _log.warning("DSE news[%s] amarstock.com fetch failed: %s", sym, e)

    # ✅ CHANGED: round-robin across the 4 website buckets (dsebd.org,
    # sharenews24.com, stocknow.com.bd, amarstock.com) instead of
    # concatenating them in collection order — each bucket is already
    # capped at PER_WEBSITE_CAP (3) above, so this just interleaves them
    # (dsebd[0], sharenews24[0], stocknow[0], amarstock[0], dsebd[1], ...)
    # so a page showing `limit` items sees a mix of all 4 sources instead
    # of e.g. 3 dsebd items followed by 3 amarstock items back-to-back.
    # A source that failed/returned nothing simply contributes 0 without
    # breaking the interleave (its slot is skipped, not left blank).
    order = ["dsebd.org", "sharenews24.com", "stocknow.com.bd", "amarstock.com"]
    merged: list[dict] = []
    for i in range(PER_WEBSITE_CAP):
        for src in order:
            bucket = groups[src]
            if i < len(bucket):
                merged.append(bucket[i])
    return merged[:limit]


# Best-effort ticker -> common company name, needed because sharenews24.com
# (and get_agm_news's company-name matching) reference companies by name,
# never by DSE trading code. Not exhaustive — extend as you cover more
# tickers. A ticker missing here still gets full bdshare coverage above
# (those match by code, not name); it just skips the sharenews24 pass and
# falls back to code-matching against get_agm_news's company column, which
# usually won't hit.
_DSE_COMPANY_NAMES_FALLBACK = {
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
    "RANFOUNDRY": "Rangpur Foundry",
}

# ✅ CHANGED: sharenews24.com (confirmed live, see Railway log sample) and
# amarstock.com write Bengali-language headlines almost exclusively -- the
# English fallback name above ("Square Pharmaceuticals") never appears in
# their text, so matching against it alone silently returns 0 every time,
# regardless of how the English matching logic is tuned. This is a
# best-effort, hand-typed set of the common Bengali forms for the same 11
# tickers -- NOT verified against live headlines from this environment
# (network-restricted sandbox), so treat these as a starting point: check
# the "sample headlines" log lines after deploying and correct any that
# don't actually match real article text.
_DSE_COMPANY_NAMES_BENGALI_FALLBACK = {
    "SQURPHARMA": ["স্কয়ার ফার্মা", "স্কয়ার ফার্মাসিউটিক্যালস"],
    "GP": ["গ্রামীণফোন"],
    "BEXIMCO": ["বেক্সিমকো"],
    "RFL": ["আরএফএল"],
    "BATBC": ["বিএটিবিসি", "ব্রিটিশ আমেরিকান টোব্যাকো"],
    "ROBI": ["রবি"],
    "WALTONHIL": ["ওয়ালটন"],
    "BRACBANK": ["ব্র্যাক ব্যাংক"],
    "ISLAMIBANK": ["ইসলামী ব্যাংক"],
    "LHBL": ["লাফার্জহোলসিম"],
    "RANFOUNDRY": ["রংপুর ফাউন্ড্রি"],
    "ABBANK": ["এবি ব্যাংক"],
}

_DSE_COMPANY_NAMES_LIVE: dict[str, str] | None = None
_DSE_COMPANY_NAMES_TS = 0.0
_DSE_COMPANY_NAMES_TTL = 6 * 60 * 60  # names rarely change; matches the ticker-list cache TTL


def _load_dse_company_names() -> dict[str, str]:
    """✅ CHANGED: full ticker -> company-name map for ALL ~650 DSE-listed
    companies, scraped once (then cached 6h) from dsebd.org's own company
    directory — instead of relying on a small hand-typed dict that only
    covers whichever tickers we happened to test (e.g. RANFOUNDRY had real
    amarstock.com coverage the whole time; we just hadn't typed its name in
    yet). The page lists entries as "TICKER (Full Company Name)" in plain
    text, so this is parsed with one regex rather than depending on exact
    table markup, which makes it more resilient to a page redesign.

    _DSE_COMPANY_NAMES_FALLBACK's hand-verified names always win over the
    parsed ones (applied last via .update()), and the whole fallback dict
    is used outright if the live fetch fails for any reason — so a
    dsebd.org outage degrades to "only the 11 verified tickers work",
    never to a crash.
    """
    global _DSE_COMPANY_NAMES_LIVE, _DSE_COMPANY_NAMES_TS
    now = _time.time()
    if _DSE_COMPANY_NAMES_LIVE is not None and (now - _DSE_COMPANY_NAMES_TS) < _DSE_COMPANY_NAMES_TTL:
        return _DSE_COMPANY_NAMES_LIVE

    try:
        import requests as _requests
        # ✅ CHANGED: dsebd.org's own certificate chain appears to be
        # genuinely broken (confirmed: fails from both a local machine and
        # from Railway, via both urllib and requests). bdshare's calls only
        # "succeed" because it automatically falls back to the alternate
        # host (dse.com.bd) whenever the primary fails for any reason,
        # SSL errors included — that fallback, not a different HTTP
        # library, is what actually made the difference. Replicating it
        # here instead of just retrying the same broken host.
        html = None
        last_exc = None
        for host in ("https://www.dsebd.org", "https://dse.com.bd"):
            try:
                with _DSEBD_CONCURRENCY:
                    resp = _requests.get(
                        f"{host}/company_listing.php",
                        headers={"User-Agent": "Mozilla/5.0 (compatible; personal-research-bot/1.0)"},
                        timeout=15,
                    )
                    resp.raise_for_status()
                    html = resp.text
                break
            except Exception as e:  # noqa: BLE001
                last_exc = e
                continue
        if html is None:
            raise last_exc or RuntimeError("both dsebd.org and dse.com.bd failed")
        from bs4 import BeautifulSoup
        text = BeautifulSoup(html, "html.parser").get_text(" ")
        pairs = re.findall(r"\b([A-Z][A-Z0-9]{1,15})\s*\(([^)]{3,80})\)", text)
        mapping = {}
        for ticker, name in pairs:
            # Some company names contain their own parens, e.g. "RAK
            # Ceramics (Bangladesh) Limited" — the regex above stops at the
            # FIRST ")", so `name` here would be the truncated fragment
            # "RAK Ceramics (Bangladesh" (dangling open paren and all).
            # That fragment is a *worse* match target than just "RAK
            # Ceramics", since a real headline is more likely to use the
            # short name alone — so trim anything from the stray "(" on.
            if "(" in name:
                name = name.split("(")[0].strip()
            if name:
                mapping[ticker.strip()] = name
        if len(mapping) < 100:  # real listing has ~650 entries — a much
            # smaller count means the page structure likely changed and
            # this regex isn't matching it correctly anymore; don't cache
            # a broken partial result, fall through to the fallback dict.
            raise ValueError(f"only parsed {len(mapping)} entries — page structure may have changed")
        mapping.update(_DSE_COMPANY_NAMES_FALLBACK)
        _DSE_COMPANY_NAMES_LIVE = mapping
        _DSE_COMPANY_NAMES_TS = now
        _log.info("Loaded %d DSE company names from dsebd.org's company listing.", len(mapping))
        return mapping
    except Exception as e:  # noqa: BLE001
        _log.warning("Could not load DSE company name listing (%s); falling back to %d hardcoded names.",
                     e, len(_DSE_COMPANY_NAMES_FALLBACK))
        return dict(_DSE_COMPANY_NAMES_FALLBACK)


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
