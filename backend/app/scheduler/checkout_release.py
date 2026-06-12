"""Stale document check-out release — deterministic scheduler job (spec 002 US4). [C-IV]

Releases pessimistic locks older than ``firm_settings.checkout_timeout_hours``
(default 24h) so a forgotten check-out never blocks the team indefinitely.
Runs as part of the daily scheduler pass; pure deterministic code, no LLM.

The DELETE runs on the audited connection, so the audit trigger records the
released lock (action + snapshot) — no hand-written audit rows. [C-III]
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)


async def release_stale_checkouts(conn: asyncpg.Connection) -> int:
    """Delete checkouts older than the firm's timeout. Returns released count."""
    timeout_hours = await conn.fetchval(
        "SELECT checkout_timeout_hours FROM firm_settings LIMIT 1"
    )
    timeout_hours = int(timeout_hours or 24)

    rows = await conn.fetch(
        """
        DELETE FROM document_checkouts
        WHERE checked_out_at < now() - ($1 * interval '1 hour')
        RETURNING document_id, checked_out_by
        """,
        timeout_hours,
    )
    if rows:
        logger.info(
            "checkout_release: released %d stale checkout(s) (> %dh): %s",
            len(rows), timeout_hours,
            [str(r["document_id"]) for r in rows],
        )
    return len(rows)
