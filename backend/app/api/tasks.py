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
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, PARALEGAL, assert_case_access, require_roles
from app.core.security import CurrentUser, CurrentUserDep
from app.models import Priority, Task, TaskCreate, TaskStatus, TaskUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

_TASK_COLS = "id, case_id, assigned_to, description, due_date, status, priority, created_at"


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


# ── GET /tasks — cross-case filtered list (FR-142) ───────────────────────────


@router.get("/tasks", response_model=list[Task])
async def list_tasks_filtered(
    user: CurrentUserDep,
    conn: Db,
    priority: Annotated[Priority | None, Query()] = None,
    status: Annotated[TaskStatus | None, Query()] = None,
    assignee_id: Annotated[UUID | None, Query()] = None,
    case_id: Annotated[UUID | None, Query()] = None,
    due_before: Annotated[date | None, Query()] = None,
    due_after: Annotated[date | None, Query()] = None,
) -> list[Task]:
    """Advanced task filtering across cases. Non-managers see only tasks on
    their assigned cases or assigned to them (same scope as case access)."""
    params: list = []
    where: list[str] = []

    def _add(clause: str, value) -> None:
        params.append(value)
        where.append(clause.format(n=len(params)))

    if priority is not None:
        _add("t.priority = ${n}", priority)
    if status is not None:
        _add("t.status = ${n}", status)
    if assignee_id is not None:
        _add("t.assigned_to = ${n}", assignee_id)
    if case_id is not None:
        _add("t.case_id = ${n}", case_id)
    if due_before is not None:
        _add("t.due_date <= ${n}", due_before)
    if due_after is not None:
        _add("t.due_date >= ${n}", due_after)

    if user.role != MANAGER:
        params.append(user.id)
        where.append(
            f"(t.assigned_to = ${len(params)} or exists ("
            f"select 1 from case_assignments ca "
            f"where ca.case_id = t.case_id and ca.user_id = ${len(params)}))"
        )

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = await conn.fetch(
        f"""
        SELECT {", ".join("t." + c.strip() for c in _TASK_COLS.split(","))}
        FROM tasks t {where_sql}
        ORDER BY t.due_date ASC NULLS LAST, t.created_at DESC
        """,
        *params,
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
        INSERT INTO tasks (case_id, assigned_to, description, due_date, status, priority)
        VALUES ($1, $2, $3, $4, 'open', $5)
        RETURNING {_TASK_COLS}
        """,
        case_id,
        body.assigned_to,
        body.description,
        body.due_date,
        body.priority,
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
