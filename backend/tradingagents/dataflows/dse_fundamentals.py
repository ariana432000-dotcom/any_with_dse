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
    """✅ FIXED: previously used a fresh `requests.get()`, which hits
    dsebd.org's incomplete certificate chain with the *default* certifi
    bundle -- the same SSL failure confirmed (live, on both a local machine
    and Railway) and fixed for the company-name listing fetch in
    app/pipeline/market_data.py. That fix works because bdshare bundles the
    missing Sectigo DV R36 intermediate into its own shared requests.Session
    (bdshare.util.helper._session) -- not because of a different host. This
    reuses that same patched session (still passing our own honest
    User-Agent per-request) instead of re-implementing SSL trust from
    scratch, and adds the dse.com.bd fallback as a genuine outage backstop
    (separate from the cert fix)."""
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
            resp = _bdshare_session.get(target, params=params, headers=HEADERS, timeout=15)
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
        # ✅ CHANGED: log the HTTP status explicitly (e.g. "403 Client Error:
        # Forbidden") rather than just the generic exception repr -- this is
        # the same displayCompany.php endpoint pattern as company_listing.php,
        # which we've already confirmed dsebd.org returns 403 for from this
        # Railway deployment. If fundamentals are silently all N/A, this line
        # is how to confirm it's the same site-wide block rather than a
        # parsing bug.
        status = getattr(getattr(e, "response", None), "status_code", "no-response")
        logger.warning("DSE fundamentals fetch failed for %s: HTTP %s — %s", ticker, status, e)
        return f"DSE fundamentals unavailable for {ticker}: HTTP {status} — {e}"

    soup = BeautifulSoup(resp.text, "html.parser")
    fields = _parse_label_value_tables(soup)
    logger.info("DSE fundamentals[%s] fetched: HTTP %s, %d bytes, %d label-value fields parsed",
                ticker, resp.status_code, len(resp.text), len(fields))

    if not fields:
        logger.warning("DSE fundamentals[%s]: page loaded (HTTP %s) but no label-value table "
                        "found -- markup likely changed, not a fetch/block issue", ticker, resp.status_code)
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


def quick_check(ticker: str, curr_date: str = None) -> dict:
    """✅ CHANGED: app/services/market_data.py's get_fundamentals_check()
    (backing the "Fundamentals Check" UI page) already called this, but it
    was never actually defined here -- every call raised AttributeError.

    Single-fetch sanity check: reuses get_fundamentals() above (the exact
    same fetch + keyword-filter path the real AI Analysis pipeline uses),
    then re-parses its output for the 4 headline numbers so a green check
    here means the full pipeline will see the same data -- no separate
    parsing logic to drift out of sync with the real one.
    """
    raw = get_fundamentals(ticker, curr_date)

    if raw.startswith("DSE fundamentals unavailable for"):
        # get_fundamentals's own except-branch string -- the request itself
        # failed (network/cert/blocked, see the HTTP status now included).
        empty = {"pe_ratio": None, "eps": None, "market_cap": None, "dividend_yield": None}
        return {"ticker": ticker, "ok": False, "status": raw, "parsed": empty, "raw_response": raw}

    if raw.startswith("No fundamentals table found"):
        # Page loaded but _parse_label_value_tables found no rows -- markup
        # likely changed, different failure mode from a fetch/block issue.
        empty = {"pe_ratio": None, "eps": None, "market_cap": None, "dividend_yield": None}
        return {"ticker": ticker, "ok": False, "status": raw, "parsed": empty, "raw_response": raw}

    def _extract(keywords, exclude=()):
        for line in raw.split("\n"):
            low = line.lower()
            if any(k in low for k in keywords) and not any(e in low for e in exclude):
                return line.split(":", 1)[-1].strip()
        return None

    parsed = {
        "pe_ratio": _extract(["pe(x)", "p/e"]),
        "eps": _extract(["eps"], exclude=("change",)),
        "market_cap": _extract(["market capitalization", "market cap"]),
        "dividend_yield": _extract(["dividend"]),
    }
    ok = any(v is not None for v in parsed.values())
    status = (
        "Fetched and parsed successfully"
        if ok
        else "Page fetched (HTTP 200) but none of PE/EPS/Market Cap/Dividend were "
             "found in the parsed rows -- dsebd.org's label wording may have "
             "changed. See raw_response below for what was actually parsed."
    )
    return {"ticker": ticker, "ok": ok, "status": status, "parsed": parsed, "raw_response": raw[:2000]}


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
