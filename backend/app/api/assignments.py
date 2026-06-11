"""Case assignment endpoints (T033): assign/unassign users to cases.

Per contracts/rest-api.md: manager or lawyer may manage assignments; a lawyer
must additionally have access to the case (assigned). Mutations go through the
audited connection — DB triggers write the audit rows [C-III].
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, assert_case_access, require_roles
from app.core.security import CurrentUser
from app.models import AssignmentCreate, CaseAssignment

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/cases/{case_id}/assignments", response_model=CaseAssignment, status_code=201)
async def create_assignment(
    case_id: UUID,
    body: AssignmentCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> CaseAssignment:
    """Assign a user to a case. 404 unknown user, 400 inactive, 409 duplicate."""
    await assert_case_access(conn, user, case_id)

    target = await conn.fetchrow(
        "SELECT id, status FROM users WHERE id = $1", body.user_id
    )
    if target is None:
        raise ApiError(404, "not_found", "المستخدم غير موجود")
    if target["status"] != "active":
        raise ApiError(400, "invalid", "لا يمكن إسناد القضية لمستخدم غير نشط")

    already = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM case_assignments WHERE case_id = $1 AND user_id = $2)",
        case_id,
        body.user_id,
        user.firm_id,
    )
    if already:
        raise ApiError(409, "already_assigned", "المستخدم مُسند بالفعل إلى هذه القضية")

    row = await conn.fetchrow(
        """
        INSERT INTO case_assignments (firm_id, case_id, user_id)
        VALUES ($3, $1, $2)
        RETURNING id, case_id, user_id, created_at
        """,
        case_id,
        body.user_id,
    )
    return CaseAssignment(**dict(row))


@router.delete("/cases/{case_id}/assignments/{user_id}", status_code=200)
async def delete_assignment(
    case_id: UUID,
    user_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> dict:
    """Unassign a user from a case; 404 if no such assignment."""
    await assert_case_access(conn, user, case_id)

    deleted = await conn.fetchval(
        "DELETE FROM case_assignments WHERE case_id = $1 AND user_id = $2 RETURNING id",
        case_id,
        user_id,
    )
    if deleted is None:
        raise ApiError(404, "not_found", "هذا المستخدم غير مُسند إلى القضية")
    return {"status": "deleted", "id": str(deleted)}
