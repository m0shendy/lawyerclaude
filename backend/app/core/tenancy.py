"""Tenant helpers for the multi-tenant SaaS deployment (WP-S2). [C-I v2]

Two concerns live here:

* ``get_firm_config`` — read a firm's ``firm_settings`` row (secrets included)
  on the SERVICE connection.  The backend legitimately needs ``llm_api_key`` /
  ``waha_key`` to operate on behalf of any active user of the firm, but the
  RLS policy on ``firm_settings`` is manager-only — so config reads for
  request handlers go through the service context, keyed EXPLICITLY by the
  caller's ``firm_id`` (never ``LIMIT 1``).  Secrets are never returned to the
  client; they only parameterize outbound calls. [C-III]

* ``active_firm_ids`` — the worker iteration set: firms whose subscription
  status still entitles them to background processing.  ``suspended`` and
  ``cancelled`` firms are skipped (no reminders, no reports, no pipeline).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.core.db import db_connection

# Columns a config read may request — everything else is rejected.
_ALLOWED_COLS = {
    "firm_name",
    "locale",
    "waha_url",
    "waha_key",
    "llm_api_key",
    "embedding_config",
    "reminder_lead_points",
    "feature_appeal_deadlines",
}

# Firms entitled to background processing / AI features.
WORKER_ELIGIBLE_STATUSES = ("trial", "active", "past_due")


async def get_firm_config(firm_id: UUID, *cols: str) -> asyncpg.Record | None:
    """Fetch selected ``firm_settings`` columns for one firm (service context).

    Args:
        firm_id: The tenant whose settings to read.
        cols:    Column names; must be in the allowlist.

    Returns:
        The row, or None if the firm has no settings row yet.
    """
    bad = set(cols) - _ALLOWED_COLS
    if bad:
        raise ValueError(f"disallowed firm_settings columns: {sorted(bad)}")
    col_sql = ", ".join(cols)
    async with db_connection(None, context="system:firm-config") as conn:
        return await conn.fetchrow(
            f"SELECT {col_sql} FROM firm_settings WHERE firm_id = $1",  # noqa: S608 — cols allowlisted above
            firm_id,
        )


async def active_firm_ids(conn: asyncpg.Connection) -> list[UUID]:
    """Firms the background workers should serve this pass."""
    rows = await conn.fetch(
        "SELECT id FROM firms WHERE status = ANY($1::text[]) ORDER BY created_at",
        list(WORKER_ELIGIBLE_STATUSES),
    )
    return [r["id"] for r in rows]
