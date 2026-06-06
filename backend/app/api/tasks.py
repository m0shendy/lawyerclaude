"""Tasks CRUD endpoints (T064). [C-III]

Endpoints (contracts/rest-api.md)
----------------------------------
  GET    /cases/{id}/tasks    — list tasks for a case
  POST   /cases/{id}/tasks    — create a task (manager, lawyer, paralegal)
  PATCH  /tasks/{id}          — update (manager or assignee)
  DELETE /tasks/{id}          — delete (manager or assignee)

All mutations go through the audited DB connection.  [C-III]
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, PARALEGAL, assert_case_access, require_roles
from app.core.security import CurrentUser, CurrentUserDep
from app.models import Task, TaskCreate, TaskUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

_TASK_COLS = "id, case_id, assigned_to, description, due_date, status, created_at"


def _row(r) -> Task:
    return Task(**dict(r))


async def _get_task_or_404(conn, task_id: UUID) -> Task:
    row = await conn.fetchrow(
        f"SELECT {_TASK_COLS} FROM tasks WHERE id = $1", task_id
    )
    if row is None:
        raise ApiError(404, "not_found", "المهمة غير موجودة")
    return _row(row)


# ── GET /cases/{id}/tasks ─────────────────────────────────────────────────────


@router.get("/cases/{case_id}/tasks", response_model=list[Task])
async def list_tasks(case_id: UUID, user: CurrentUserDep, conn: Db) -> list[Task]:
    await assert_case_access(conn, user, case_id)
    rows = await conn.fetch(
        f"SELECT {_TASK_COLS} FROM tasks WHERE case_id = $1 ORDER BY created_at DESC",
        case_id,
    )
    return [_row(r) for r in rows]


# ── POST /cases/{id}/tasks ────────────────────────────────────────────────────


@router.post("/cases/{case_id}/tasks", response_model=Task, status_code=201)
async def create_task(
    case_id: UUID,
    body: TaskCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL))],
) -> Task:
    await assert_case_access(conn, user, case_id)

    target = await conn.fetchrow(
        "SELECT id, status FROM users WHERE id = $1", body.assigned_to
    )
    if target is None:
        raise ApiError(404, "not_found", "المستخدم المُكلَّف غير موجود")
    if target["status"] != "active":
        raise ApiError(400, "invalid", "لا يمكن تكليف مستخدم غير نشط")

    row = await conn.fetchrow(
        f"""
        INSERT INTO tasks (case_id, assigned_to, description, due_date, status)
        VALUES ($1, $2, $3, $4, 'open')
        RETURNING {_TASK_COLS}
        """,
        case_id,
        body.assigned_to,
        body.description,
        body.due_date,
    )
    return _row(row)


# ── PATCH /tasks/{id} ─────────────────────────────────────────────────────────


@router.patch("/tasks/{task_id}", response_model=Task)
async def update_task(
    task_id: UUID, body: TaskUpdate, user: CurrentUserDep, conn: Db
) -> Task:
    existing = await _get_task_or_404(conn, task_id)
    await assert_case_access(conn, user, existing.case_id)

    if user.role not in (MANAGER,) and user.id != existing.assigned_to:
        raise ApiError(
            403, "forbidden", "يمكن تعديل المهمة فقط من قِبَل مديرها أو المكلَّف بها"
        )

    updates = body.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return existing

    if "assigned_to" in updates:
        target = await conn.fetchrow(
            "SELECT id, status FROM users WHERE id = $1", updates["assigned_to"]
        )
        if target is None:
            raise ApiError(404, "not_found", "المستخدم المُكلَّف غير موجود")
        if target["status"] != "active":
            raise ApiError(400, "invalid", "لا يمكن تكليف مستخدم غير نشط")

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(task_id)

    row = await conn.fetchrow(
        f"""
        UPDATE tasks SET {", ".join(parts)}, updated_at = now()
        WHERE id = ${len(params)}
        RETURNING {_TASK_COLS}
        """,
        *params,
    )
    if row is None:
        raise ApiError(404, "not_found", "المهمة غير موجودة")
    return _row(row)


# ── DELETE /tasks/{id} ────────────────────────────────────────────────────────


@router.delete("/tasks/{task_id}", status_code=200)
async def delete_task(
    task_id: UUID, user: CurrentUserDep, conn: Db
) -> dict:
    existing = await _get_task_or_404(conn, task_id)
    await assert_case_access(conn, user, existing.case_id)

    if user.role not in (MANAGER,) and user.id != existing.assigned_to:
        raise ApiError(
            403, "forbidden", "يمكن حذف المهمة فقط من قِبَل مديرها أو المكلَّف بها"
        )

    deleted = await conn.fetchval(
        "DELETE FROM tasks WHERE id = $1 RETURNING id", task_id
    )
    if deleted is None:
        raise ApiError(404, "not_found", "المهمة غير موجودة")
    return {"status": "deleted", "id": str(deleted)}
