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
# ✅ CHANGED: no longer overriding a User-Agent here -- _throttled_get now
# goes through bdshare's own safe_get(), which uses bdshare's own session
# headers (already proven working across this site's other endpoints).
DSE_REQUEST_DELAY_SECONDS = 2.0  # be polite -- there's no public API

_last_request_ts = 0.0


def _throttled_get(url, params=None):
    """🔴 FIXED (still 403ing after the User-Agent fix -- confirmed live):
    dropping our own UA override wasn't enough by itself. bdshare ships
    its own get_company_info(), which hits this EXACT same
    displayCompany.php endpoint successfully, via its safe_get() helper --
    which retries up to 3 times with exponential back-off AND tries both
    the primary and alt host on every single attempt (up to 6 tries total
    by default), instead of the one-shot, no-retry fetch this function
    was doing. If dsebd.org's 403 here is a transient rate-limit/WAF
    flake rather than a hard, permanent IP-level block, that retry
    resilience is very plausibly the actual difference between "works"
    (bdshare's OHLCV/news calls, and bdshare's own get_company_info) and
    "doesn't" (this function, one attempt, no retry). Reusing bdshare's
    own proven safe_get() directly -- rather than reimplementing a
    thinner version of the same retry/fallback logic ourselves -- is the
    more robust fix. This only changes HOW the HTML is fetched; our own
    downstream parsing (_parse_label_value_tables) is unchanged, since we
    need label:value pairs, not bdshare's pd.read_html() table shape.
    If this STILL 403s after retries, that's strong evidence the block is
    IP-based (e.g. Railway's datacenter range flagged) rather than
    request-shape-based -- test the same code from a non-datacenter
    connection to confirm."""
    from bdshare.util.helper import BDShareError, safe_get

    global _last_request_ts
    elapsed = time.time() - _last_request_ts
    if elapsed < DSE_REQUEST_DELAY_SECONDS:
        time.sleep(DSE_REQUEST_DELAY_SECONDS - elapsed)

    try:
        resp = safe_get(
            url, params=params,
            alt_url=ALT_BASE_URL if url == BASE_URL else None,
            retries=3, pause=1.0, timeout=15,
        )
        return resp
    except BDShareError as e:
        # Re-raise as requests.RequestException so get_fundamentals()'s
        # existing `except requests.RequestException` still catches this
        # without needing its own change -- BDShareError is a plain
        # Exception subclass, not a RequestException one.
        raise requests.RequestException(str(e)) from e
    finally:
        _last_request_ts = time.time()


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


def quick_check(ticker: str, curr_date: str = None) -> dict:
    """Standalone sanity-check for the UI's "Fundamentals Check" page/route
    (see app/api/routes/stocks.py's /fundamentals/check and
    app/services/market_data.py's get_fundamentals_check). Calls
    get_fundamentals() directly -- one HTTP fetch, no LLM call, no other
    analysts, no LangGraph pipeline -- so you can verify a scrape/parsing
    fix in a couple seconds instead of waiting through a full multi-agent
    AI Analysis run.

    Mirrors the keyword-matching g_dse() logic in
    app/pipeline/agents.py's create_fundamentals_analyst. Kept as a small,
    independent copy rather than a shared import: this needs to keep
    working even if that function's internals change shape, and the two
    call sites have different failure-handling needs (this one returns a
    structured status for a UI card; that one silently falls back to
    "N/A" per-field for an LLM prompt).
    """
    raw = get_fundamentals(ticker, curr_date)

    def _find(keywords, exclude=()):
        for line in raw.split("\n"):
            low = line.lower()
            if any(k in low for k in keywords) and not any(e in low for e in exclude):
                import re
                m = re.search(r"(-?[\d,]+\.?\d*)", line.split(":", 1)[-1])
                if m:
                    return m.group(1).replace(",", "")
        return None

    parsed = {
        "pe_ratio": _find(["pe(x)", "p/e"]),
        "eps": _find(["eps"], exclude=("change",)),
        "market_cap": _find(["market capitalization", "market cap"]),
        "dividend_yield": _find(["dividend"]),
    }

    if raw.startswith("DSE fundamentals snapshot"):
        ok, status = True, "OK -- live snapshot fetched from dsebd.org successfully."
    elif raw.startswith("DSE fundamentals unavailable"):
        ok, status = False, ("FAILED -- the request to dsebd.org/dse.com.bd itself errored "
                              "(network, cert, or a block like 403). See raw_response below.")
    elif raw.startswith("No fundamentals table found"):
        ok, status = False, ("FAILED -- the page loaded but didn't parse into label:value rows "
                              "(markup may have changed, or dsebd.org served something other "
                              "than the real company page).")
    else:
        ok, status = False, "UNKNOWN -- unexpected response shape, see raw_response below."

    return {
        "ticker": ticker.upper(),
        "ok": ok,
        "status": status,
        "parsed": parsed,
        "raw_response": raw[:500],
    }


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
