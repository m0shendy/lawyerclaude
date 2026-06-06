"""Background pipeline worker (T043).

Polls the ``documents`` table for rows in ``status = 'pending'`` and drives
each through the full ingestion pipeline (OCR → normalize → chunk → embed).

Run with (CWD = ``backend/``):

    python -m workers.pipeline_worker

Or via the Docker ``CMD`` / ``ENTRYPOINT`` worker variant.

Design
------
* APScheduler ``BlockingScheduler`` with an ``IntervalTrigger`` fires every
  ``settings.worker_poll_seconds`` seconds (default 5).
* Each tick claims ONE pending document (``FOR UPDATE SKIP LOCKED``) to avoid
  two worker processes colliding.  Scaling to multiple workers is safe because
  the pipeline ``run.py`` uses a compare-and-swap on the status transition.
* The worker never routes reminders/reports (that is the scheduler_worker).
  [C-IV]
* All mutations go through ``db_connection(None, context='worker:pipeline')``,
  so the audit triggers record system-level pipeline actions. [C-III]
* Errors are logged and the document is marked 'failed' — the worker never
  crashes the scheduler on a per-document error.

Graceful shutdown
-----------------
SIGINT / SIGTERM are handled by APScheduler's blocking scheduler; it waits for
the currently running job to finish before stopping.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings
from app.core.db import close_pool, db_connection
from app.pipeline.run import process_document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("workers.pipeline_worker")


async def _tick() -> None:
    """One scheduler tick: claim and process a single pending document."""
    try:
        async with db_connection(None, context="worker:pipeline:poll") as conn:
            # Claim exactly one pending document — SKIP LOCKED prevents two
            # workers from racing for the same row.
            row = await conn.fetchrow(
                """
                SELECT id FROM documents
                WHERE status = 'pending'
                ORDER BY uploaded_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
            )

        if row is None:
            return  # nothing to do this tick

        doc_id = row["id"]
        logger.info("pipeline_worker: processing document %s", doc_id)
        try:
            await process_document(doc_id)
        except Exception:
            # process_document already marks the document 'failed' and logs the
            # error; we catch here to prevent the scheduler from stopping.
            logger.exception(
                "pipeline_worker: unhandled exception for document %s", doc_id
            )
    finally:
        # _run_tick() uses asyncio.run(), which creates a FRESH event loop every
        # tick. An asyncpg pool is bound to the loop that created it, so reusing
        # the module-global pool on the next tick's loop raises "Event loop is
        # closed". Dispose the pool each tick so the next tick rebuilds it on
        # its own loop.
        await close_pool()


def _run_tick() -> None:
    """Synchronous wrapper called by APScheduler."""
    asyncio.run(_tick())


def main() -> None:
    settings = get_settings()
    interval = settings.worker_poll_seconds

    scheduler = BlockingScheduler()
    scheduler.add_job(
        _run_tick,
        trigger=IntervalTrigger(seconds=interval),
        id="pipeline_poll",
        max_instances=1,
        coalesce=True,  # skip missed ticks instead of catching up
    )

    logger.info(
        "pipeline_worker: starting — polling every %ds", interval
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("pipeline_worker: shutting down")
    finally:
        asyncio.run(close_pool())


if __name__ == "__main__":
    main()
