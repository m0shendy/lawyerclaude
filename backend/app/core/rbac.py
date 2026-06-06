"""Server-side RBAC (T021). [C-I]

Role checks are enforced server-side on every endpoint (the frontend guards
are UX only). Case-level access = manager OR assigned via case_assignments.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import Depends

from app.core.errors import ApiError
from app.core.security import CurrentUser, get_current_user

MANAGER = "partner_manager"
LAWYER = "lawyer"
PARALEGAL = "paralegal"
SECRETARY = "secretary"

ALL_ROLES = (MANAGER, LAWYER, PARALEGAL, SECRETARY)


def require_roles(*roles: str):
    """Dependency factory: 403 unless the caller's role is one of `roles`."""

    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise ApiError(403, "forbidden", "صلاحياتك لا تسمح بهذا الإجراء")
        return user

    return _check


async def is_assigned_to_case(conn: asyncpg.Connection, user_id: UUID, case_id: UUID) -> bool:
    return bool(
        await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM case_assignments WHERE case_id = $1 AND user_id = $2)",
            case_id,
            user_id,
        )
    )


async def assert_case_access(
    conn: asyncpg.Connection,
    user: CurrentUser,
    case_id: UUID,
    *,
    manager_ok: bool = True,
) -> None:
    """404 if the case doesn't exist; 403 if neither assigned nor (optionally) manager.

    Out-of-scope reads return 404 (not 403) so non-assigned users cannot probe
    for case existence (contract: '404 not found/out-of-scope').
    """
    exists = await conn.fetchval("SELECT EXISTS (SELECT 1 FROM cases WHERE id = $1)", case_id)
    if not exists:
        raise ApiError(404, "not_found", "القضية غير موجودة")
    if manager_ok and user.role == MANAGER:
        return
    if await is_assigned_to_case(conn, user.id, case_id):
        return
    raise ApiError(404, "not_found", "القضية غير موجودة")
