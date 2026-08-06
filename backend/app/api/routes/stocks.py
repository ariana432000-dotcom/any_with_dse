"""Stock market-data routes — live (keyless Yahoo/Stooq) by default."""

from __future__ import annotations

from fastapi import APIRouter, Query, UploadFile, File, Form, HTTPException

from app.services import market_data as mds

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/{ticker}/quote")
async def quote(ticker: str) -> dict:
    return await mds.get_quote(ticker)


@router.get("/{ticker}/history")
async def history(ticker: str, days: int = Query(220, ge=5, le=2000)) -> dict:
    return await mds.get_history(ticker, days_back=days)


@router.get("/{ticker}/news")
async def news(ticker: str, limit: int = Query(8, ge=1, le=30), refresh: bool = Query(False)) -> dict:
    return {"ticker": ticker.upper(), "items": await mds.get_news(ticker, limit, refresh=refresh)}


@router.get("/{ticker}/news/debug")
async def news_debug(ticker: str, limit: int = Query(8, ge=1, le=30)) -> dict:
    """Uncached diagnostics for the DSE news path -- per-source hit counts
    and, when a ticker had zero sharenews24 matches, a sample of the
    cached article titles it was checked against. Lets you see WHY a
    ticker got fewer/no sharenews24 results without digging through
    Railway's Deploy Logs."""
    import asyncio

    return await asyncio.to_thread(mds.get_news_debug, ticker, limit)


@router.get("/{ticker}/fundamentals/check")
async def fundamentals_check(ticker: str) -> dict:
    """✅ CHANGED: this route was missing entirely -- the frontend's
    "Fundamentals Check" page (stocksApi.fundamentalsCheck in
    frontend/src/lib/api.ts) already called GET /stocks/{ticker}/
    fundamentals/check, which 404'd since app.services.market_data's
    get_fundamentals_check() existed but was never wired to a route."""
    return await mds.get_fundamentals_check(ticker)


# ✅ ADDED — dsebd.org's robots.txt disallows automated download of annual
# reports (and the site actively 403s bot-like traffic on adjacent pages,
# see dse_fundamentals.py's own comments), so the server can never fetch
# these PDFs itself. This is the human-driven alternative: you download
# the annual report PDF yourself in a browser, then upload it here -- the
# server just stores + reads it, never crawls dsebd.org for it.
@router.get("/{ticker}/reports")
async def list_reports(ticker: str) -> dict:
    """Which fiscal-year PDFs are already on disk for this ticker, and
    whether each has been through LLM extraction yet (cached) -- lets the
    upload page show "already have 2024, 2025" instead of re-asking."""
    return await mds.list_dse_reports(ticker.upper())


@router.post("/{ticker}/reports/upload")
async def upload_report(
    ticker: str,
    fiscal_year: str = Form(..., description="e.g. 2025, or 2024-2025"),
    file: UploadFile = File(...),
) -> dict:
    if file.content_type not in ("application/pdf", "application/octet-stream") and not (
        file.filename or ""
    ).lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    contents = await file.read()
    if not contents.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="File doesn't look like a valid PDF.")
    # 25MB ceiling -- generous for an annual report, cheap protection
    # against something enormous filling up the Railway volume.
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 25MB).")
    saved_path = await mds.save_dse_report(ticker.upper(), fiscal_year.strip(), contents)
    return {"ticker": ticker.upper(), "fiscal_year": fiscal_year.strip(), "saved_to": saved_path, "bytes": len(contents)}
