"""Deterministic scheduler worker — Component C (T065). [C-IV]

Fires the daily reminder pass at the firm-local hour
(``settings.scheduler_reminder_hour``, default 08:00 Africa/Cairo).  The pass
itself (``app.scheduler.reminders.run_reminders``) is pure, deterministic code:
it decides *when* and *to whom* reminders go and writes a ``notifications_log``
row for every attempt.  No LLM or agent is ever on this path [C-IV].

Run with (CWD = ``backend/``)::

    python -m workers.scheduler_worker

Or via the Docker worker entrypoint variant.

Why a daily cron (not a poll loop): lead points are calendar-date based
(``due_date - Nd``), so a single pass per firm-local day is sufficient and
deterministic.  ``--once`` runs a single pass immediately (used by the Phase 6
verification in quickstart §7 and by ops to force a run).

Manager daily reports (Phase 7, T071–T073) will register a second job on this
same scheduler.

Event-loop note: like the pipeline worker, each tick uses ``asyncio.run`` (a
fresh loop) and disposes the asyncpg pool afterwards, because a pool is bound to
the loop that created it.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.db import close_pool, db_connection
from app.scheduler.reminders import run_all_reminders
from app.scheduler.reports import run_all_reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("workers.scheduler_worker")


async def _reminder_pass() -> None:
    """One deterministic reminder pass over the firm's data."""
    try:
        # user=None → BYPASSRLS service pool; the scheduler legitimately sees all
        # rows. context tags the audit GUCs as a system action. [C-III]
        async with db_connection(None, context="worker:scheduler:reminders") as conn:
            summary = await run_all_reminders(conn)
        logger.info("scheduler_worker: reminder pass %s", summary.as_dict())
    except Exception:
        # Never let one failing pass stop the scheduler.
        logger.exception("scheduler_worker: reminder pass failed")
    finally:
        await close_pool()


def _run_reminder_pass() -> None:
    """Synchronous wrapper called by APScheduler / --once."""
    asyncio.run(_reminder_pass())


async def _report_pass() -> None:
    """One deterministic daily-report pass: assemble → phrase → send → log. [C-IV]"""
    try:
        async with db_connection(None, context="worker:scheduler:reports") as conn:
            counts = await run_all_reports(conn)
        logger.info("scheduler_worker: report pass %s", counts)
    except Exception:
        logger.exception("scheduler_worker: report pass failed")
    finally:
        await close_pool()


def _run_report_pass() -> None:
    """Synchronous wrapper called by APScheduler / --reports-once."""
    asyncio.run(_report_pass())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Deterministic scheduler (Component C)")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single reminder pass immediately and exit.",
    )
    parser.add_argument(
        "--reports-once",
        action="store_true",
        help="Run a single daily-report pass immediately and exit.",
    )
    args = parser.parse_args(argv)

    if args.once:
        logger.info("scheduler_worker: running a single reminder pass (--once)")
        _run_reminder_pass()
        return

    if args.reports_once:
        logger.info("scheduler_worker: running a single report pass (--reports-once)")
        _run_report_pass()
        return

    settings = get_settings()
    hour = settings.scheduler_reminder_hour

    scheduler = BlockingScheduler(timezone="Africa/Cairo")
    scheduler.add_job(
        _run_reminder_pass,
        trigger=CronTrigger(hour=hour, minute=0),
        id="daily_reminders",
        max_instances=1,
        coalesce=True,
    )
    # Manager daily reports — same firm-local morning, 30 min after reminders so
    # the two passes never contend for the pool. [C-IV]
    scheduler.add_job(
        _run_report_pass,
        trigger=CronTrigger(hour=hour, minute=30),
        id="daily_reports",
        max_instances=1,
        coalesce=True,
    )

    logger.info(
        "scheduler_worker: starting — reminders %02d:00, reports %02d:30 (Africa/Cairo)",
        hour, hour,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler_worker: shutting down")
    finally:
        asyncio.run(close_pool())


if __name__ == "__main__":
    main()
