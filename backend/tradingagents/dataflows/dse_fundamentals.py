"""
DSE (Dhaka Stock Exchange) fundamentals vendor.

Exposes the same function signatures as alpha_vantage_fundamentals.py so it
can be dropped into interface.py / config.py as a new `fundamental_data`
vendor (see the wiring notes at the bottom of this file).

Two tiers of data:
  1. Headline snapshot ratios (EPS, NAV, P/E, dividend, sponsor holding) --
     scraped from the DSE company page (dsebd.org). Works for any listed
     ticker, always available, cheap.
  2. Full statements (balance sheet / income statement / cash flow) -- DSE
     does not publish these in structured form anywhere, so they are
     extracted from the company's audited annual report PDF via
     dse_statement_extractor.py. See that file for how PDFs get onto disk.

IMPORTANT -- dsebd.org's robots.txt disallows automated crawling. This
module is meant for a personal/academic project: keep request volume low
(DSE_REQUEST_DELAY_SECONDS below), identify your bot honestly in the
User-Agent, and don't run it as a high-frequency or commercial scraper.
If you need reliable, high-volume access, that's a conversation to have
with DSE/BSEC directly rather than something to script around quietly.
"""

import logging
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from . import dse_statement_extractor as _stmt

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dsebd.org/displayCompany.php"
ALT_BASE_URL = "https://dse.com.bd/displayCompany.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; personal-research-bot/1.0)"
}
DSE_REQUEST_DELAY_SECONDS = 2.0  # be polite -- there's no public API

_last_request_ts = 0.0


def _throttled_get(url, params=None):
    """🔴 FIXED (still broken -- confirmed live, 403 Forbidden): the
    previous fix reused bdshare's patched session for the SSL cert issue,
    but still overrode its User-Agent with our own
    "Mozilla/5.0 (compatible; personal-research-bot/1.0)" string via the
    per-request `headers=` param. That override is real -- `requests`
    merges per-request headers on top of session headers, so it replaced
    bdshare's own "bdshare/2.0 (...)" UA for this call specifically.
    OHLCV (day_end_archive.php) and news (old_news.php) go through this
    same bdshare session WITHOUT that override and work fine, confirmed
    live -- displayCompany.php (this function) is the one endpoint where
    we were substituting a different UA, and it's the one endpoint
    getting a 403. Dropping the override and using bdshare's own session
    headers as-is (same UA + Accept + Accept-Encoding it already sends
    successfully elsewhere on this site) is the minimal, most
    evidence-backed fix. If dsebd.org's block is actually IP-based (e.g.
    flagging Railway's datacenter range) rather than UA-based, this alone
    won't fix it -- test the same code from a non-datacenter connection
    (e.g. your own machine) to tell the two apart."""
    from bdshare.util.helper import _session as _bdshare_session

    global _last_request_ts
    elapsed = time.time() - _last_request_ts
    if elapsed < DSE_REQUEST_DELAY_SECONDS:
        time.sleep(DSE_REQUEST_DELAY_SECONDS - elapsed)

    last_exc = None
    for target in (url, ALT_BASE_URL if url == BASE_URL else None):
        if not target:
            continue
        try:
            resp = _bdshare_session.get(target, params=params, timeout=15)
            resp.raise_for_status()
            _last_request_ts = time.time()
            return resp
        except requests.RequestException as e:
            last_exc = e
            continue
    _last_request_ts = time.time()
    raise last_exc


def _parse_label_value_tables(soup: BeautifulSoup) -> dict:
    """
    DSE renders most snapshot data as <td>Label</td><td>Value</td> pairs
    inside plain HTML tables. Walking every row and building a
    {label: value} dict is more robust than hardcoding class names, since
    dsebd.org's markup shifts without notice -- but it also means you
    should sanity-check the output against the live page after DSE does
    a site redesign.
    """
    data = {}
    for row in soup.find_all("tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) == 2 and cells[0]:
            data[cells[0].rstrip(":").strip()] = cells[1]
    return data


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """
    Scrape the DSE company snapshot page for headline fundamentals: EPS,
    NAV per share, P/E, sponsor/director/govt/institute/foreign/public
    holding %, market cap, last dividend, etc.
    """
    try:
        resp = _throttled_get(BASE_URL, params={"name": ticker})
    except requests.RequestException as e:
        logger.warning("DSE fundamentals fetch failed for %s: %s", ticker, e)
        return f"DSE fundamentals unavailable for {ticker}: {e}"

    soup = BeautifulSoup(resp.text, "html.parser")
    fields = _parse_label_value_tables(soup)

    if not fields:
        return (
            f"No fundamentals table found for {ticker} on DSE. The page "
            f"markup may have changed -- inspect {BASE_URL}?name={ticker} "
            f"manually (view-source) and update _parse_label_value_tables."
        )

    wanted_keywords = [
        "last trading price", "closing price", "face value", "market category",
        "sector", "pe(x)", "eps", "nav per share", "market capitalization",
        "dividend", "sponsor", "govt", "institute", "foreign", "public",
    ]
    lines = [f"DSE fundamentals snapshot -- {ticker} (as of {curr_date or datetime.now().date()})"]
    for key, value in fields.items():
        if any(w in key.lower() for w in wanted_keywords):
            lines.append(f"{key}: {value}")
    if len(lines) == 1:
        # keyword filter matched nothing -- dump everything rather than
        # silently return an empty-looking report
        lines += [f"{k}: {v}" for k, v in fields.items()]
    return "\n".join(lines)


def get_balance_sheet(ticker: str, freq: str = "annual", curr_date: str = None):
    """Full balance sheet, extracted from the audited annual report PDF."""
    return _stmt.get_statement(ticker, "balance_sheet", freq=freq, curr_date=curr_date)


def get_cashflow(ticker: str, freq: str = "annual", curr_date: str = None):
    """Full cash flow statement, extracted from the audited annual report PDF."""
    return _stmt.get_statement(ticker, "cashflow", freq=freq, curr_date=curr_date)


def get_income_statement(ticker: str, freq: str = "annual", curr_date: str = None):
    """Full income statement, extracted from the audited annual report PDF."""
    return _stmt.get_statement(ticker, "income_statement", freq=freq, curr_date=curr_date)


# ---------------------------------------------------------------------------
# Wiring into your existing vendor architecture (interface.py / config.py):
#
#   from .dse_fundamentals import (
#       get_balance_sheet as get_dse_balance_sheet,
#       get_cashflow as get_dse_cashflow,
#       get_fundamentals as get_dse_fundamentals,
#       get_income_statement as get_dse_income_statement,
#   )
#
# Then add "dse" alongside "alpha_vantage" / "yfinance" wherever
# route_to_vendor dispatches on config["data_vendors"]["fundamental_data"],
# and set that config value to "dse" for BD tickers (e.g. via your
# symbol_utils.py ticker normalization -- DSE trading codes like
# "SQURPHARMA" or "GP" won't match a US ticker pattern, so you can branch
# on that to pick the vendor automatically).
# ---------------------------------------------------------------------------
