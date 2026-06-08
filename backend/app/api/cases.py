"""Cases endpoints (T032): /cases CRUD per contracts/rest-api.md.

RBAC is enforced server-side: managers see everything; everyone else only the
cases they are assigned to via case_assignments (role-scoped in SQL). Every
mutation runs on the audited connection (Db) — the DB triggers write the
audit rows [C-III]; no hand-written audit entries here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, assert_case_access, require_roles
from app.core.security import CurrentUser, CurrentUserDep
from app.models import (
    AiOutputType,
    Case,
    CaseCreate,
    CaseUpdate,
    Deadline,
    Document,
    ReviewState,
    Role,
    Task,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_CASE_COLUMNS = (
    "id, title, client_name, case_number, court, case_type, status, "
    "practice_area, jurisdiction, opposing_counsel, docket_number, tags, "
    "priority, stage, created_by, created_at"
)


# ── response composites (detail view) ────────────────────────────────────────


class AiOutputSummary(BaseModel):
    """Slim ai_outputs projection for the case detail — no content/grounding here."""

    id: UUID
    type: AiOutputType
    review_state: ReviewState
    low_confidence_flag: bool
    created_at: datetime


class AssignmentWithUser(BaseModel):
    id: UUID
    case_id: UUID
    user_id: UUID
    created_at: datetime
    full_name: str
    role: Role


class CaseDetail(Case):
    documents: list[Document]
    ai_outputs: list[AiOutputSummary]
    deadlines: list[Deadline]
    tasks: list[Task]
    assignments: list[AssignmentWithUser]


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.get("/cases", response_model=list[Case])
async def list_cases(user: CurrentUserDep, conn: Db) -> list[Case]:
    """Role-scoped list: manager → all cases; others → assigned cases only."""
    if user.role == MANAGER:
        rows = await conn.fetch(
            f"SELECT {_CASE_COLUMNS} FROM cases ORDER BY created_at DESC"
        )
    else:
        rows = await conn.fetch(
            f"""
            SELECT {_CASE_COLUMNS}
            FROM cases c
            JOIN case_assignments ca ON ca.case_id = c.id
            WHERE ca.user_id = $1
            ORDER BY c.created_at DESC
            """,
            user.id,
        )
    return [Case(**dict(r)) for r in rows]


@router.post("/cases", response_model=Case, status_code=201)
async def create_case(
    body: CaseCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> Case:
    """Create a case (manager, lawyer). A creating lawyer is auto-assigned so
    the case is visible to them under the role-scoped list/detail rules."""
    async with conn.transaction():
        row = await conn.fetchrow(
            f"""
            INSERT INTO cases (title, client_name, case_number, court, case_type, status,
                               practice_area, jurisdiction, opposing_counsel, docket_number,
                               tags, priority, stage, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING {_CASE_COLUMNS}
            """,
            body.title,
            body.client_name,
            body.case_number,
            body.court,
            body.case_type,
            body.status,
            body.practice_area,
            body.jurisdiction,
            body.opposing_counsel,
            body.docket_number,
            body.tags,
            body.priority,
            body.stage,
            user.id,
        )
        if user.role == LAWYER:
            await conn.execute(
                "INSERT INTO case_assignments (case_id, user_id) VALUES ($1, $2)",
                row["id"],
                user.id,
            )
    return Case(**dict(row))


@router.get("/cases/{case_id}", response_model=CaseDetail)
async def get_case(case_id: UUID, user: CurrentUserDep, conn: Db) -> CaseDetail:
    """Case detail with nested documents, ai_outputs (slim), deadlines, tasks,
    assignments — assigned users or manager only (404 for out-of-scope)."""
    await assert_case_access(conn, user, case_id)

    case_row = await conn.fetchrow(
        f"SELECT {_CASE_COLUMNS} FROM cases WHERE id = $1", case_id
    )
    if case_row is None:  # raced delete between access check and read
        raise ApiError(404, "not_found", "القضية غير موجودة")

    documents = await conn.fetch(
        """
        SELECT id, case_id, file_path, file_name, source_type, status,
               ocr_confidence, error_detail, uploaded_by, uploaded_at
        FROM documents WHERE case_id = $1 ORDER BY uploaded_at DESC
        """,
        case_id,
    )
    ai_outputs = await conn.fetch(
        """
        SELECT id, type, review_state, low_confidence_flag, created_at
        FROM ai_outputs WHERE case_id = $1 ORDER BY created_at DESC
        """,
        case_id,
    )
    deadlines = await conn.fetch(
        """
        SELECT id, case_id, type, title, basis, due_date, suggested_date, confirmed,
               confirmed_by, confirmed_at, responsible_user_id, derived_from_document_id,
               low_confidence_flag, acknowledged_at, created_at
        FROM deadlines WHERE case_id = $1 ORDER BY due_date ASC
        """,
        case_id,
    )
    tasks = await conn.fetch(
        """
        SELECT id, case_id, assigned_to, description, due_date, status, created_at
        FROM tasks WHERE case_id = $1 ORDER BY created_at DESC
        """,
        case_id,
    )
    assignments = await conn.fetch(
        """
        SELECT ca.id, ca.case_id, ca.user_id, ca.created_at, u.full_name, u.role
        FROM case_assignments ca
        JOIN users u ON u.id = ca.user_id
        WHERE ca.case_id = $1
        ORDER BY ca.created_at ASC
        """,
        case_id,
    )

    return CaseDetail(
        **dict(case_row),
        documents=[Document(**dict(r)) for r in documents],
        ai_outputs=[AiOutputSummary(**dict(r)) for r in ai_outputs],
        deadlines=[Deadline(**dict(r)) for r in deadlines],
        tasks=[Task(**dict(r)) for r in tasks],
        assignments=[AssignmentWithUser(**dict(r)) for r in assignments],
    )


@router.patch("/cases/{case_id}", response_model=Case)
async def update_case(
    case_id: UUID, body: CaseUpdate, user: CurrentUserDep, conn: Db
) -> Case:
    """Partial update — manager or *assigned lawyer* only; an assigned
    paralegal/secretary gets 403 (they can see the case, not edit it)."""
    await assert_case_access(conn, user, case_id)
    if user.role not in (MANAGER, LAWYER):
        raise ApiError(403, "forbidden", "صلاحياتك لا تسمح بتعديل القضية")

    updates = body.model_dump(exclude_unset=True)
    for field in ("title", "client_name", "status"):
        if field in updates and updates[field] is None:
            raise ApiError(400, "validation_error", "لا يمكن أن يكون هذا الحقل فارغًا")

    if not updates:
        row = await conn.fetchrow(
            f"SELECT {_CASE_COLUMNS} FROM cases WHERE id = $1", case_id
        )
        return Case(**dict(row))

    set_clauses = []
    params: list = []
    for i, (field, value) in enumerate(updates.items(), start=1):
        set_clauses.append(f"{field} = ${i}")
        params.append(value)
    params.append(case_id)
    row = await conn.fetchrow(
        f"""
        UPDATE cases
        SET {", ".join(set_clauses)}, updated_at = now()
        WHERE id = ${len(params)}
        RETURNING {_CASE_COLUMNS}
        """,
        *params,
    )
    if row is None:
        raise ApiError(404, "not_found", "القضية غير موجودة")
    return Case(**dict(row))


@router.delete("/cases/{case_id}", status_code=200)
async def delete_case(
    case_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER))],
) -> dict:
    """Delete a case (manager only). The audit trigger captures the snapshot."""
    deleted = await conn.fetchval(
        "DELETE FROM cases WHERE id = $1 RETURNING id", case_id
    )
    if deleted is None:
        raise ApiError(404, "not_found", "القضية غير موجودة")
    return {"status": "deleted", "id": str(deleted)}
