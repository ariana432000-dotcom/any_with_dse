"""
Background worker.

Runs an async scheduler that, on an interval, refreshes market data for the
watchlist and publishes a heartbeat event over the WebSocket bus. It also
drives the periodic dataset-export job: every ~DATASET_JOB_INTERVAL_SECONDS
(default 2h), while the market is open, it runs one full analysis per
watchlist ticker and appends the result to that ticker's CSV under
DATASET_CSV_PATH — building a growing historical dataset of fetched data +
agent decisions over time without any separate scheduler infrastructure.
"""

from __future__ import annotations

import asyncio
import signal
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.api.ws import publish_event
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.services import market_data as mds

setup_logging()
log = get_logger("app.workers.scheduler")

MARKET_TZ = ZoneInfo("America/New_York")

# In-process overlap guard: a batch across N tickers can legitimately take a
# long time on local CPU inference, so we must never let a new 2h trigger
# stack a second batch on top of one still running.
_dataset_job_running = False


async def refresh_market_data() -> None:
    """Pull fresh quotes for the watchlist and push them to clients."""
    from app.services.watchlist_store import WatchlistStore

    try:
        tickers = await WatchlistStore.list_tickers()
    except Exception as e:  # noqa: BLE001
        log.debug("watchlist unavailable (%s); using configured default", e)
        tickers = settings.watch_tickers

    for ticker in tickers:
        try:
            quote = await mds.get_quote(ticker)
            await publish_event({"type": "quote", "data": quote})
            log.info("refreshed %s: %s", ticker, quote.get("price"))
        except Exception as e:  # noqa: BLE001
            log.warning("refresh failed for %s: %s", ticker, e)


def is_market_open_now() -> bool:
    """US equities regular session: 9:30-16:00 America/New_York, Mon-Fri.
    Deliberately does not account for market holidays (no holiday calendar
    here) — worst case the job fires a few extra times a year on a closed
    day, which is harmless (the analysis still runs against the last
    available close)."""
    now = datetime.now(MARKET_TZ)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= now <= close_t


async def _get_last_dataset_run() -> datetime | None:
    from app.db.mongo import get_mongo

    try:
        doc = await get_mongo()["scheduler_state"].find_one({"_id": "dataset_job"})
    except Exception as e:  # noqa: BLE001
        log.debug("dataset job last-run lookup failed: %s", e)
        return None
    raw = (doc or {}).get("last_run")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


async def _set_last_dataset_run(ts: datetime) -> None:
    from app.db.mongo import get_mongo

    try:
        await get_mongo()["scheduler_state"].update_one(
            {"_id": "dataset_job"}, {"$set": {"last_run": ts.isoformat()}}, upsert=True,
        )
    except Exception as e:  # noqa: BLE001
        log.debug("dataset job last-run persist failed: %s", e)


async def run_dataset_job_for_ticker(ticker: str) -> None:
    """One full analysis for one ticker, appended to its CSV on success.
    Hard-capped so a stuck/slow model call can't wedge the job forever."""
    from app.ai_engine.execution import get_execution_service
    from app.ai_engine.state import ExecutionRequest
    from app.services import dataset_writer

    service = get_execution_service()
    request = ExecutionRequest(ticker=ticker)
    try:
        state = await asyncio.wait_for(
            service.run_sync(request),
            timeout=settings.DATASET_JOB_PER_TICKER_TIMEOUT_SECONDS,
        )
        dataset_writer.append_row(state)
        sig = state.recommendation.signal.value if state.recommendation else "N/A"
        conf = (state.recommendation.confidence * 100) if state.recommendation else 0.0
        log.info("dataset job: %s -> %s (confidence %.0f%%)", ticker, sig, conf)
    except asyncio.TimeoutError:
        log.warning("dataset job: %s timed out after %ss, skipping",
                    ticker, settings.DATASET_JOB_PER_TICKER_TIMEOUT_SECONDS)
    except Exception as e:  # noqa: BLE001
        log.warning("dataset job failed for %s: %s", ticker, e)


async def run_dataset_job() -> None:
    """Runs one full analysis per watchlist ticker, sequentially (local CPU
    inference doesn't parallelize well on a single Ollama instance), appending
    each completed run to its CSV dataset."""
    from app.services.watchlist_store import WatchlistStore

    try:
        tickers = await WatchlistStore.list_tickers()
    except Exception as e:  # noqa: BLE001
        log.warning("dataset job: couldn't load watchlist (%s); using configured default", e)
        tickers = settings.watch_tickers

    log.info("dataset job starting for %d ticker(s): %s", len(tickers), tickers)
    for ticker in tickers:
        await run_dataset_job_for_ticker(ticker)
    log.info("dataset job finished")


async def maybe_trigger_dataset_job() -> None:
    """Called every heartbeat tick. Fires the dataset job as a detached task
    (never blocking the quote-refresh heartbeat) at most once per
    DATASET_JOB_INTERVAL_SECONDS, gated to market hours if configured."""
    global _dataset_job_running
    if _dataset_job_running:
        return
    if settings.DATASET_JOB_MARKET_HOURS_ONLY and not is_market_open_now():
        return

    now = datetime.now(timezone.utc)
    last_run = await _get_last_dataset_run()
    if last_run is not None and (now - last_run).total_seconds() < settings.DATASET_JOB_INTERVAL_SECONDS:
        return

    _dataset_job_running = True
    # Claim the slot immediately (before the batch even starts) so a second
    # tick landing while this one is still setting up can't double-fire.
    await _set_last_dataset_run(now)

    async def _guarded() -> None:
        global _dataset_job_running
        try:
            await run_dataset_job()
        except Exception as e:  # noqa: BLE001
            log.exception("dataset job crashed: %s", e)
        finally:
            _dataset_job_running = False

    asyncio.create_task(_guarded())


async def main() -> None:
    log.info(
        "Worker started — interval=%ss tickers=%s",
        settings.WORKER_INTERVAL_SECONDS, settings.watch_tickers,
    )
    stop = asyncio.Event()

    def _stop(*_):
        log.info("Worker stopping…")
        stop.set()

    with_signals = True
    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, _stop)
        loop.add_signal_handler(signal.SIGINT, _stop)
    except NotImplementedError:  # e.g. Windows
        with_signals = False

    while not stop.is_set():
        await publish_event({
            "type": "heartbeat",
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        await refresh_market_data()
        await maybe_trigger_dataset_job()
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.WORKER_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    if not with_signals:
        return


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
