"""Dataset API — read access to the per-ticker CSV files the scheduled
dataset-export job (app/workers/scheduler.py) builds over time.

    GET /dataset                    one entry per ticker CSV (rows, updated_at)
    GET /dataset/{ticker}           parsed rows for one ticker, newest first
    GET /dataset/{ticker}/download  the raw CSV file
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import settings
from app.services import dataset_writer

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.get("")
async def list_datasets() -> dict:
    return {"datasets": dataset_writer.list_datasets()}


@router.get("/{ticker}")
async def get_dataset(ticker: str, limit: int = Query(500, ge=1, le=5000)) -> dict:
    rows = dataset_writer.read_rows(ticker, limit)
    return {"ticker": ticker.upper(), "rows": rows}


@router.get("/{ticker}/download")
async def download_dataset(ticker: str) -> FileResponse:
    path = os.path.join(settings.DATASET_CSV_PATH, f"{ticker.upper()}.csv")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No dataset file for this ticker yet")
    return FileResponse(path, media_type="text/csv", filename=f"{ticker.upper()}.csv")
