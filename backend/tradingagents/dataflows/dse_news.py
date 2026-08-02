"""
DSE news vendor -- combines two sources:

  1. dsebd.org's news archive, via `bdshare.get_all_news` /
     `bdshare.get_price_sensitive_news` -- per-ticker corporate disclosures
     (EPS, NAV, dividend, AGM, etc.). Uses the maintained `bdshare` library
     (see dse_stock_data.py's docstring for why) instead of the hand-rolled
     scraper this file originally shipped with -- bdshare parses the same
     news_archive.php endpoint with a proper row parser and dual-host
     fallback, which is more reliable than guessing the table structure.

  2. sharenews24.com -- general Bangladeshi share-market news (market
     commentary, macro, IPO news). Plain server-rendered HTML, no JS
     rendering needed, not covered by bdshare. Not ticker-structured, so
     ticker-matching here is a best-effort keyword search over headlines --
     verify/tighten the selector against the live page if results look noisy.

Matches the get_news / get_global_news contract from news_data_tools.py, so
this registers as a "news_data" vendor exactly like yfinance_news.py.

Install: pip install bdshare beautifulsoup4 requests
"""

import logging
import time

import pandas as pd
from bdshare import BDShareError, get_all_news, get_price_sensitive_news

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-research-bot/1.0)"}
SHARENEWS24_REQUEST_DELAY_SECONDS = 2.0
_last_sharenews24_ts = 0.0

SHARENEWS24_BASE = "https://sharenews24.com"
DEFAULT_ARTICLE_LIMIT = 20


def _throttled_get(url: str) -> requests.Response:
    global _last_sharenews24_ts
    elapsed = time.time() - _last_sharenews24_ts
    if elapsed < SHARENEWS24_REQUEST_DELAY_SECONDS:
        time.sleep(SHARENEWS24_REQUEST_DELAY_SECONDS - elapsed)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    _last_sharenews24_ts = time.time()
    resp.raise_for_status()
    return resp


def _row_to_line(row: pd.Series) -> str:
    """bdshare's news rows carry varying columns depending on the source
    page (date/symbol/headline/details); print whatever is present rather
    than assuming a fixed schema."""
    parts = [str(v) for v in row.values if pd.notna(v) and str(v).strip()]
    return " | ".join(parts)


def _fetch_dsebd_news(ticker: str = None, start_date: str = None, end_date: str = None) -> list[str]:
    try:
        df = get_all_news(start=start_date, end=end_date, code=ticker)
    except BDShareError as e:
        logger.info("bdshare get_all_news returned nothing for %s: %s", ticker, e)
        return []
    except Exception as e:
        logger.warning("bdshare get_all_news failed for %s: %s", ticker, e)
        return []
    return [_row_to_line(row) for _, row in df.iterrows()]


def _fetch_price_sensitive_news(ticker: str = None) -> list[str]:
    try:
        df = get_price_sensitive_news(code=ticker)
    except BDShareError as e:
        logger.info("bdshare get_price_sensitive_news returned nothing for %s: %s", ticker, e)
        return []
    except Exception as e:
        logger.warning("bdshare get_price_sensitive_news failed for %s: %s", ticker, e)
        return []
    return [_row_to_line(row) for _, row in df.iterrows()]


def _fetch_sharenews24(query: str = None, limit: int = DEFAULT_ARTICLE_LIMIT) -> list[dict]:
    """
    Scrapes sharenews24.com's homepage for headlines. `query` (company name
    or ticker) is matched against headline text -- best-effort, not
    guaranteed, since this site isn't ticker-structured.
    """
    try:
        resp = _throttled_get(SHARENEWS24_BASE)
    except requests.RequestException as e:
        logger.warning("sharenews24 fetch failed: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []
    for link in soup.find_all("a", href=True):
        title = link.get_text(strip=True)
        if len(title) < 15:
            continue
        if query and query.lower() not in title.lower():
            continue
        href = link["href"]
        full_link = href if href.startswith("http") else f"{SHARENEWS24_BASE}{href}"
        articles.append({"text": title, "link": full_link})
        if len(articles) >= limit:
            break
    return articles


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Per-ticker news: bdshare's dsebd disclosures in the date range +
    price-sensitive news + best-effort sharenews24 headline matches."""
    dsebd_lines = _fetch_dsebd_news(ticker=ticker, start_date=start_date, end_date=end_date)
    sensitive_lines = _fetch_price_sensitive_news(ticker=ticker)
    sharenews_articles = _fetch_sharenews24(query=ticker)

    if not dsebd_lines and not sensitive_lines and not sharenews_articles:
        return f"No DSE news found for {ticker} between {start_date} and {end_date}."

    lines = [f"DSE news for {ticker} ({start_date} to {end_date}):"]
    lines += [f"[dsebd.org] {line}" for line in dsebd_lines]
    lines += [f"[dsebd.org price-sensitive] {line}" for line in sensitive_lines]
    lines += [f"[sharenews24.com] {a['text']} ({a['link']})" for a in sharenews_articles]
    return "\n".join(lines)


def get_global_news(curr_date: str, look_back_days: int = None, limit: int = None) -> str:
    """General DSE/market news: bdshare's all-market disclosures + recent
    price-sensitive news + sharenews24 front-page headlines, no ticker filter."""
    from datetime import datetime, timedelta

    look_back_days = look_back_days or 7
    limit = limit or DEFAULT_ARTICLE_LIMIT
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)).strftime("%Y-%m-%d")

    dsebd_lines = _fetch_dsebd_news(start_date=start_date, end_date=curr_date)[:limit]
    sensitive_lines = _fetch_price_sensitive_news()[:limit]
    sharenews_articles = _fetch_sharenews24(limit=limit)

    lines = [f"DSE market news (last {look_back_days} days as of {curr_date}):"]
    lines += [f"[dsebd.org] {line}" for line in dsebd_lines]
    lines += [f"[dsebd.org price-sensitive] {line}" for line in sensitive_lines]
    lines += [f"[sharenews24.com] {a['text']} ({a['link']})" for a in sharenews_articles]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Wiring into interface.py (see dse_fundamentals.py's comment for the pattern):
#   from .dse_news import get_news as get_dse_news, get_global_news as get_dse_global_news
# Register "dse" as a news_data vendor option alongside yfinance/alpha_vantage.
# ---------------------------------------------------------------------------
