"""
DSE news vendor -- combines two sources:

  1. dsebd.org's Extended News Search (news_archive.php) -- per-ticker
     corporate disclosures/announcements (EPS, NAV, dividend, AGM, etc.),
     searchable by trading code and date range. Same site as
     dse_fundamentals.py -- same robots.txt caution applies, so this
     reuses the same conservative, throttled request pattern.

  2. sharenews24.com -- general Bangladeshi share-market news (market
     commentary, macro, IPO news). Plain server-rendered HTML, no JS
     rendering needed. Not ticker-structured, so ticker-matching here is
     a best-effort keyword search over headlines, not a guaranteed hit.

Matches the get_news / get_global_news contract from news_data_tools.py
(route_to_vendor dispatch), so this can register as a "news_data" vendor
exactly like yfinance_news.py / alpha_vantage_news.py.

CAUTION -- two things to verify/adjust before relying on this:
  - dsebd.org's robots.txt disallows automated crawling. Keep
    DSE_REQUEST_DELAY_SECONDS conservative; this is meant for a personal/
    academic project, not a high-frequency scraper.
  - I could not fetch the live dsebd.org or sharenews24.com pages myself
    (robots block on the former; wanted to keep both consistent), so the
    form field names in _fetch_dsebd_news (symbol/startDate/endDate) and
    the generic <a>-tag scraping in _fetch_sharenews24 are best-effort
    guesses at the page structure. View-source (or Inspect) the live
    pages and adjust the selectors/param names if results come back empty
    or noisy -- treat this file as a working first draft, not a verified
    final scraper.
"""

import logging
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-research-bot/1.0)"}
DSE_REQUEST_DELAY_SECONDS = 2.0
_last_request_ts = 0.0

DSEBD_NEWS_URL = "https://www.dsebd.org/news_archive.php"
SHARENEWS24_BASE = "https://sharenews24.com"

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_ARTICLE_LIMIT = 20


def _throttled_get(url: str, params: dict | None = None) -> requests.Response:
    global _last_request_ts
    elapsed = time.time() - _last_request_ts
    if elapsed < DSE_REQUEST_DELAY_SECONDS:
        time.sleep(DSE_REQUEST_DELAY_SECONDS - elapsed)
    resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
    _last_request_ts = time.time()
    resp.raise_for_status()
    return resp


def _fetch_dsebd_news(ticker: str = None, start_date: str = None, end_date: str = None) -> list[dict]:
    """
    Queries dsebd.org's Extended News Search. Pass `ticker` for
    per-company disclosures, or leave it None for all-market news in the
    date range.
    """
    params = {}
    if ticker:
        params["symbol"] = ticker
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    try:
        resp = _throttled_get(DSEBD_NEWS_URL, params=params)
    except requests.RequestException as e:
        logger.warning("dsebd news fetch failed: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = []
    # dsebd renders each news item as a table row with a trading-code
    # label followed by title/body text. Walking every row defensively
    # (rather than depending on exact class names) is more resilient to
    # markup changes, at the cost of picking up some noise -- filter by
    # length as a cheap signal-vs-chrome heuristic.
    for row in soup.find_all("tr"):
        text = row.get_text(" ", strip=True)
        if len(text) > 20:
            articles.append({"source": "dsebd.org", "text": text, "ticker": ticker})
    return articles


def _fetch_sharenews24(query: str = None, limit: int = DEFAULT_ARTICLE_LIMIT) -> list[dict]:
    """
    Scrapes sharenews24.com's homepage for headlines. `query` (company
    name or ticker) is matched against headline text -- this site isn't
    ticker-structured so it's a best-effort keyword filter.
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
        articles.append({"source": "sharenews24.com", "text": title, "link": full_link})
        if len(articles) >= limit:
            break
    return articles


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Per-ticker news: dsebd disclosures in the date range + best-effort
    sharenews24 headline matches for the ticker/company name."""
    dsebd_articles = _fetch_dsebd_news(ticker=ticker, start_date=start_date, end_date=end_date)
    sharenews_articles = _fetch_sharenews24(query=ticker)

    if not dsebd_articles and not sharenews_articles:
        return f"No DSE news found for {ticker} between {start_date} and {end_date}."

    lines = [f"DSE news for {ticker} ({start_date} to {end_date}):"]
    lines += [f"[dsebd.org] {a['text']}" for a in dsebd_articles]
    lines += [f"[sharenews24.com] {a['text']} ({a['link']})" for a in sharenews_articles]
    return "\n".join(lines)


def get_global_news(curr_date: str, look_back_days: int = None, limit: int = None) -> str:
    """General DSE/market news: dsebd all-market disclosures + sharenews24
    front-page headlines, no ticker filter."""
    look_back_days = look_back_days or DEFAULT_LOOKBACK_DAYS
    limit = limit or DEFAULT_ARTICLE_LIMIT

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=look_back_days)

    dsebd_articles = _fetch_dsebd_news(
        start_date=start_dt.strftime("%Y-%m-%d"), end_date=curr_date
    )[:limit]
    sharenews_articles = _fetch_sharenews24(limit=limit)

    lines = [f"DSE market news (last {look_back_days} days as of {curr_date}):"]
    lines += [f"[dsebd.org] {a['text']}" for a in dsebd_articles]
    lines += [f"[sharenews24.com] {a['text']} ({a['link']})" for a in sharenews_articles]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Wiring into interface.py (same pattern as dse_fundamentals.py):
#
#   from .dse_news import (
#       get_news as get_dse_news,
#       get_global_news as get_dse_global_news,
#   )
#
# Register "dse" as a news_data vendor option alongside yfinance/alpha_vantage.
# ---------------------------------------------------------------------------
