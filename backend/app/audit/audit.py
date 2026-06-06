"""Audit helpers (T024). [C-III]

The audit WRITING is done by DB triggers (0005) — application code never
hand-writes audit rows for entity mutations, so no code path can skip them.
What lives here:
  * read helpers for the manager-only audit viewer (T036);
  * verification helpers used by smoke tests (T042) to prove an action was
    captured and that the log is append-only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def fetch_audit_entries(
    conn: asyncpg.Connection,
    *,
    entity_table: str | None = None,
    record_id: UUID | None = None,
    who_user_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Read-only audit query for the manager viewer."""
    conditions: list[str] = []
    params: list[Any] = []
    if entity_table:
        params.append(entity_table)
        conditions.append(f"entity_table = ${len(params)}")
    if record_id:
        params.append(record_id)
        conditions.append(f"record_id = ${len(params)}")
    if who_user_id:
        params.append(who_user_id)
        conditions.append(f"who_user_id = ${len(params)}")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    limit_idx = len(params)
    params.append(offset)
    offset_idx = len(params)
    rows = await conn.fetch(
        f"""
        SELECT id, who_user_id, who_role, when_ts, entity_table, record_id,
               action::text AS action, change_detail, context
        FROM audit_log
        {where}
        ORDER BY when_ts DESC, id DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def verify_audited(
    conn: asyncpg.Connection,
    entity_table: str,
    record_id: UUID,
    action: str,
) -> bool:
    """True if an audit row exists for (table, record, action) — used in tests."""
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM audit_log
                WHERE entity_table = $1 AND record_id = $2 AND action = $3::audit_action
            )
            """,
            entity_table,
            record_id,
            action,
        )
    )


async def verify_append_only(conn: asyncpg.Connection) -> bool:
    """True if the audit log rejects UPDATE/DELETE (append-only proof). [C-III]"""
    try:
        await conn.execute("UPDATE audit_log SET context = 'tamper' WHERE id = (SELECT min(id) FROM audit_log)")
        return False  # update succeeded — append-only is BROKEN
    except asyncpg.PostgresError:
        pass
    try:
        await conn.execute("DELETE FROM audit_log WHERE id = (SELECT min(id) FROM audit_log)")
        return False
    except asyncpg.PostgresError:
        return True
