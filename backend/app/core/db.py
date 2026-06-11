"""Database access (T019).

Raw parameterized SQL over an asyncpg pool — no ORM. Every request-scoped
connection carries the audit GUCs (app.user_id / app.user_role / app.context)
so the DB audit triggers capture who/role/context for every mutation. [C-III]
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Annotated

import asyncpg
from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.security import CurrentUser, get_current_user

_pool: asyncpg.Pool | None = None
_service_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Lazy app_user pool (RLS-enforced) — used for API request contexts."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(get_settings().database_url, min_size=1, max_size=10)
    return _pool


async def get_service_pool() -> asyncpg.Pool:
    """Lazy BYPASSRLS service pool — used for system/worker contexts (user=None).

    Background workers operate across all rows legitimately, so they must not be
    filtered by RLS. Falls back to database_url if service_database_url is unset
    (in which case RLS would hide rows from workers — it MUST be configured).
    """
    global _service_pool
    if _service_pool is None:
        settings = get_settings()
        url = settings.service_database_url or settings.database_url
        _service_pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
    return _service_pool


async def close_pool() -> None:
    global _pool, _service_pool
    if _pool is not None:
        await _pool.close()
        _pool = None
    if _service_pool is not None:
        await _service_pool.close()
        _service_pool = None


async def _set_audit_gucs(
    conn: asyncpg.Connection,
    user: "CurrentUser | None",
    context: str | None,
) -> None:
    """Stamp the connection with acting identity for the audit triggers and RLS.

    app.firm_id drives tenant isolation (0013): every RLS policy fails closed
    when it is unset, so API connections MUST carry it. Workers that legitimately
    span firms use the service pool (BYPASSRLS) and pass firm per-iteration. [C-I][C-III]
    """
    await conn.execute(
        "SELECT set_config('app.user_id', $1, false),"
        "       set_config('app.user_role', $2, false),"
        "       set_config('app.firm_id', $3, false),"
        "       set_config('app.context', $4, false)",
        str(user.id) if user else "",
        user.role if user else "",
        str(user.firm_id) if user else "",
        context or "",
    )


@contextlib.asynccontextmanager
async def db_connection(
    user: "CurrentUser | None" = None,
    context: str | None = None,
) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection with audit GUCs set; reset on release.

    Workers pass user=None with a context like 'worker:pipeline' — the audit
    row then records a system action (who_user_id null, context set).
    """
    # System contexts (user=None: background workers, auth resolution) use the
    # BYPASSRLS service pool so RLS doesn't hide rows from them. API requests
    # (user set) use the RLS-enforced app_user pool.
    pool = await (get_service_pool() if user is None else get_pool())
    conn = await pool.acquire()
    try:
        await _set_audit_gucs(conn, user, context)
        yield conn
    finally:
        with contextlib.suppress(Exception):
            await conn.execute("RESET ALL")
        await pool.release(conn)


async def get_db(
    request: Request,
    _user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AsyncIterator[asyncpg.Connection]:
    """FastAPI dependency: per-request connection carrying the caller's identity.

    Depends on get_current_user so authentication ALWAYS resolves first and sets
    request.state.current_user BEFORE we stamp the audit/RLS GUCs — independent of
    the path operation's parameter order. Without this, a handler that lists
    `conn: Db` ahead of its user dependency would stamp empty GUCs and every RLS
    write would fail. context = method + path.
    """
    user: CurrentUser | None = getattr(request.state, "current_user", None)
    context = f"{request.method} {request.url.path}"
    async with db_connection(user, context) as conn:
        yield conn


Db = Annotated[asyncpg.Connection, Depends(get_db)]
