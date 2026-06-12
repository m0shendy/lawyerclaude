"""Operator authentication chain for the platform admin console (feature 003).

require_operator — FastAPI dependency:
  ES256 JWT → aal2 assurance → active platform_operators row →
  operator_sessions row < 30 min idle (touch last_seen on success,
  purge + 401 on stale).  Any failure ⇒ 401/403 with empty body (FR-312).
  Firm-role tokens ⇒ 403 + audit row (FR-303). [C-I][C-III]

service_admin_conn — async context manager that yields an asyncpg Connection
  from the service pool (BYPASSRLS) with operator audit GUCs set.

audit_admin_read — inserts an admin_read audit row for explicit cross-firm
  detail reads and audit-viewer queries (FR-311).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.db import get_service_pool
from app.core.errors import ApiError
from app.core.security import _decode_token

_IDLE_TIMEOUT = timedelta(minutes=30)
_bearer = HTTPBearer(auto_error=False)


class OperatorContext(BaseModel):
    operator_id: UUID
    display_name: str
    session_id: str


async def require_operator(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> OperatorContext:
    """Fail-closed operator guard — every link in the chain must succeed."""
    if credentials is None:
        raise ApiError(401, "unauthorized", "")

    claims = _decode_token(credentials.credentials)

    # Require aal2 (TOTP MFA completed)
    aal = claims.get("aal") or (claims.get("amr") and _extract_aal(claims))
    if aal != "aal2":
        raise ApiError(401, "unauthorized", "")

    auth_user_id = claims.get("sub")
    if not auth_user_id:
        raise ApiError(401, "unauthorized", "")

    # GoTrue session_id from JWT
    session_id = claims.get("session_id") or claims.get("jti")
    if not session_id:
        raise ApiError(401, "unauthorized", "")

    pool = await get_service_pool()
    conn = await pool.acquire()
    try:
        # Check platform_operators allowlist
        op_row = await conn.fetchrow(
            "SELECT auth_user_id, display_name, is_active FROM platform_operators WHERE auth_user_id = $1",
            UUID(auth_user_id),
        )
        if op_row is None:
            # Firm-role token on /admin/* → 403 + audit
            await _audit_forbidden_firm_token(conn, auth_user_id, request)
            raise ApiError(403, "forbidden", "")
        if not op_row["is_active"]:
            raise ApiError(403, "forbidden", "")

        # Check / touch operator session
        now = datetime.now(tz=timezone.utc)
        stale_before = now - _IDLE_TIMEOUT
        sess = await conn.fetchrow(
            "SELECT last_seen FROM operator_sessions WHERE session_id = $1 AND operator_id = $2",
            session_id,
            UUID(auth_user_id),
        )
        if sess is None:
            raise ApiError(401, "unauthorized", "")
        if sess["last_seen"] < stale_before:
            # Purge stale session lazily
            await conn.execute(
                "DELETE FROM operator_sessions WHERE session_id = $1",
                session_id,
            )
            raise ApiError(401, "unauthorized", "")

        # Touch last_seen
        await conn.execute(
            "UPDATE operator_sessions SET last_seen = now() WHERE session_id = $1",
            session_id,
        )
    finally:
        await pool.release(conn)

    ctx = OperatorContext(
        operator_id=UUID(auth_user_id),
        display_name=op_row["display_name"],
        session_id=session_id,
    )
    request.state.operator = ctx
    return ctx


def _extract_aal(claims: dict) -> str | None:
    """Supabase Cloud encodes aal in the amr array when GoTrue issues aal2 tokens."""
    for entry in claims.get("amr", []):
        if isinstance(entry, dict) and entry.get("method") == "totp":
            return "aal2"
    return None


async def _audit_forbidden_firm_token(
    conn: asyncpg.Connection,
    auth_user_id: str,
    request: Request,
) -> None:
    """Log a firm-role token attempting an /admin/* route (FR-303)."""
    try:
        await conn.execute(
            """
            INSERT INTO audit_log (who_user_id, who_role, entity_table, action, context)
            VALUES ($1, 'unknown_firm_role', 'admin_access', 'create', $2)
            """,
            UUID(auth_user_id),
            f"FORBIDDEN firm-role token on {request.method} {request.url.path}",
        )
    except Exception:
        pass  # audit best-effort; do not mask the 403


@contextlib.asynccontextmanager
async def service_admin_conn(
    operator: OperatorContext,
) -> AsyncIterator[asyncpg.Connection]:
    """Yield a service-connection with operator audit GUCs set.

    All writes through this connection hit the existing audit triggers with the
    operator's identity recorded as who_user_id / who_role / context. [C-III]
    """
    pool = await get_service_pool()
    conn = await pool.acquire()
    try:
        await conn.execute(
            "SELECT set_config('app.user_id', $1, false),"
            "       set_config('app.user_role', $2, false),"
            "       set_config('app.context', $3, false)",
            str(operator.operator_id),
            "platform_operator",
            "platform_admin",
        )
        yield conn
    finally:
        with contextlib.suppress(Exception):
            await conn.execute("RESET ALL")
        await pool.release(conn)


async def audit_admin_read(
    conn: asyncpg.Connection,
    entity: str,
    record_id: UUID | str | None,
    firm_id: UUID | str | None,
    operator: OperatorContext,
) -> None:
    """Insert an explicit admin_read audit row for cross-firm detail reads (FR-311)."""
    await conn.execute(
        """
        INSERT INTO audit_log (who_user_id, who_role, entity_table, record_id, action, firm_id, context)
        VALUES ($1, 'platform_operator', $2, $3, 'create', $4, 'platform_admin:read')
        """,
        operator.operator_id,
        entity,
        UUID(str(record_id)) if record_id else None,
        UUID(str(firm_id)) if firm_id else None,
    )


OperatorDep = Annotated[OperatorContext, Depends(require_operator)]
