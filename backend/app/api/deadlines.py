"""Deadlines & obligations endpoints (T063). [C-IV][C-X]

Endpoints (contracts/rest-api.md)
----------------------------------
  GET    /cases/{id}/deadlines            — list (general + appeal suggestions)
  POST   /cases/{id}/deadlines            — create general deadline
  PATCH  /deadlines/{id}                  — update (manager / assigned lawyer)
  DELETE /deadlines/{id}                  — delete (manager / assigned lawyer)
  POST   /deadlines/{id}/confirm          — confirm an appeal suggestion [C-X]
  POST   /deadlines/{id}/acknowledge      — lawyer acknowledges (resets escalation clock)

Constitution invariants
-----------------------
[C-IV]  Reminders are fired by the DETERMINISTIC scheduler, never by this code.
        This file only manages the data rows; the scheduler reads confirmed rows.
[C-X]   Appeal-type deadlines (appeal_istinaf / mu_arada / naqd) are created as
        suggestions (confirmed=false) by the system (see US5 / T076-T081) and
        are INERT — no notifications — until the responsible lawyer confirms.
        The feature flag gate (feature_appeal_deadlines) is enforced here for
        the confirm endpoint.
[C-III] Every create/update/delete is audited via the DB trigger connection.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.db import Db
from app.core.errors import ApiError
from app.core.flags import require_flag
from app.core.rbac import LAWYER, MANAGER, assert_case_access, require_roles
from app.core.security import CurrentUser, CurrentUserDep
from app.models import Deadline, DeadlineCreate, DeadlineUpdate
from app.scheduler.appeal_deadlines import suggest_appeal_deadlines

logger = logging.getLogger(__name__)

router = APIRouter()

_DEADLINE_COLS = (
    "id, case_id, type, title, basis, due_date, suggested_date, confirmed, "
    "confirmed_by, confirmed_at, responsible_user_id, derived_from_document_id, "
    "low_confidence_flag, acknowledged_at, created_at"
)


def _row(r) -> Deadline:
    return Deadline(**dict(r))


async def _get_deadline_or_404(conn, deadline_id: UUID) -> Deadline:
    row = await conn.fetchrow(
        f"SELECT {_DEADLINE_COLS} FROM deadlines WHERE id = $1", deadline_id
    )
    if row is None:
        raise ApiError(404, "not_found", "الموعد غير موجود")
    return _row(row)


# ── GET /cases/{id}/deadlines ─────────────────────────────────────────────────


@router.get("/cases/{case_id}/deadlines", response_model=list[Deadline])
async def list_deadlines(case_id: UUID, user: CurrentUserDep, conn: Db) -> list[Deadline]:
    await assert_case_access(conn, user, case_id)
    rows = await conn.fetch(
        f"SELECT {_DEADLINE_COLS} FROM deadlines WHERE case_id = $1 ORDER BY due_date ASC",
        case_id,
    )
    return [_row(r) for r in rows]


# ── POST /cases/{id}/deadlines ────────────────────────────────────────────────


@router.post("/cases/{case_id}/deadlines", response_model=Deadline, status_code=201)
async def create_deadline(
    case_id: UUID,
    body: DeadlineCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> Deadline:
    """Create a GENERAL deadline (type='general').

    Appeal-type suggestions are created by the system (T076-T081).  A user
    cannot create an appeal-type deadline directly as a fact. [C-X]
    """
    await assert_case_access(conn, user, case_id)

    # Verify the responsible user exists and is active.
    target = await conn.fetchrow(
        "SELECT id, status FROM users WHERE id = $1", body.responsible_user_id
    )
    if target is None:
        raise ApiError(404, "not_found", "المستخدم المسؤول غير موجود")
    if target["status"] != "active":
        raise ApiError(400, "invalid", "لا يمكن إسناد الموعد لمستخدم غير نشط")

    row = await conn.fetchrow(
        f"""
        INSERT INTO deadlines
            (case_id, type, title, basis, due_date, confirmed,
             responsible_user_id, low_confidence_flag)
        VALUES ($1, 'general', $2, $3, $4, true, $5, false)
        RETURNING {_DEADLINE_COLS}
        """,
        case_id,
        body.title,
        body.basis,
        body.due_date,
        body.responsible_user_id,
    )
    return _row(row)


# ── POST /cases/{id}/deadlines/appeal-suggestions (T077) [C-X] ────────────────


class AppealSuggestRequest(BaseModel):
    judgment_date: date
    responsible_user_id: UUID
    derived_from_document_id: UUID | None = None
    low_confidence_flag: bool = False


@router.post(
    "/cases/{case_id}/deadlines/appeal-suggestions",
    response_model=list[Deadline],
    status_code=201,
)
async def generate_appeal_suggestions(
    case_id: UUID,
    body: AppealSuggestRequest,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> list[Deadline]:
    """Generate appeal-deadline **suggestions** (``confirmed=false``) for a case. [C-X]

    Double-gated: the ``feature_appeal_deadlines`` flag must be on AND the
    expert-supplied appeal periods must be populated (they are EMPTY until expert
    sign-off — see ``scheduler/appeal_deadlines.py``). Until then this returns an
    empty list. Suggestions never notify until the responsible lawyer confirms.
    """
    await require_flag(conn, "feature_appeal_deadlines")
    await assert_case_access(conn, user, case_id)

    target = await conn.fetchrow(
        "SELECT id, status FROM users WHERE id = $1", body.responsible_user_id
    )
    if target is None:
        raise ApiError(404, "not_found", "المستخدم المسؤول غير موجود")
    if target["status"] != "active":
        raise ApiError(400, "invalid", "لا يمكن إسناد الموعد لمستخدم غير نشط")

    suggestions = suggest_appeal_deadlines(
        body.judgment_date,
        responsible_user_id=body.responsible_user_id,
        derived_from_document_id=body.derived_from_document_id,
        low_confidence_flag=body.low_confidence_flag,
    )

    created: list[Deadline] = []
    for s in suggestions:
        row = await conn.fetchrow(
            f"""
            INSERT INTO deadlines
                (case_id, type, title, basis, due_date, suggested_date, confirmed,
                 responsible_user_id, derived_from_document_id, low_confidence_flag)
            VALUES ($1, $2, $3, $4, $5, $6, false, $7, $8, $9)
            RETURNING {_DEADLINE_COLS}
            """,
            case_id, s["type"], s["title"], s["basis"], s["due_date"],
            s["suggested_date"], s["responsible_user_id"],
            s["derived_from_document_id"], s["low_confidence_flag"],
        )
        created.append(_row(row))

    logger.info(
        "appeal suggestions generated: case=%s count=%d (flag on)", case_id, len(created)
    )
    return created


# ── PATCH /deadlines/{id} ─────────────────────────────────────────────────────


@router.patch("/deadlines/{deadline_id}", response_model=Deadline)
async def update_deadline(
    deadline_id: UUID,
    body: DeadlineUpdate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> Deadline:
    existing = await _get_deadline_or_404(conn, deadline_id)
    await assert_case_access(conn, user, existing.case_id)

    updates = body.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return existing

    # Validate new responsible_user if changing.
    if "responsible_user_id" in updates:
        target = await conn.fetchrow(
            "SELECT id, status FROM users WHERE id = $1", updates["responsible_user_id"]
        )
        if target is None:
            raise ApiError(404, "not_found", "المستخدم المسؤول غير موجود")
        if target["status"] != "active":
            raise ApiError(400, "invalid", "لا يمكن إسناد الموعد لمستخدم غير نشط")

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(deadline_id)

    row = await conn.fetchrow(
        f"""
        UPDATE deadlines SET {", ".join(parts)}, updated_at = now()
        WHERE id = ${len(params)}
        RETURNING {_DEADLINE_COLS}
        """,
        *params,
    )
    if row is None:
        raise ApiError(404, "not_found", "الموعد غير موجود")
    return _row(row)


# ── DELETE /deadlines/{id} ────────────────────────────────────────────────────


@router.delete("/deadlines/{deadline_id}", status_code=200)
async def delete_deadline(
    deadline_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> dict:
    existing = await _get_deadline_or_404(conn, deadline_id)
    await assert_case_access(conn, user, existing.case_id)

    deleted = await conn.fetchval(
        "DELETE FROM deadlines WHERE id = $1 RETURNING id", deadline_id
    )
    if deleted is None:
        raise ApiError(404, "not_found", "الموعد غير موجود")
    return {"status": "deleted", "id": str(deleted)}


# ── POST /deadlines/{id}/confirm — confirm an appeal suggestion [C-X] ─────────


@router.post("/deadlines/{deadline_id}/confirm", response_model=Deadline)
async def confirm_deadline(
    deadline_id: UUID, user: CurrentUserDep, conn: Db
) -> Deadline:
    """Confirm an appeal-type suggestion.

    Only the **responsible lawyer** (the one named on the deadline) may confirm.
    The feature flag must be on.  After confirmation reminders will schedule.
    [C-X]
    """
    await require_flag(conn, "feature_appeal_deadlines")

    existing = await _get_deadline_or_404(conn, deadline_id)
    await assert_case_access(conn, user, existing.case_id)

    if existing.type == "general":
        raise ApiError(
            400,
            "invalid_state",
            "المواعيد العامة مؤكَّدة تلقائياً — هذا الإجراء خاص بمقترحات الطعون",
        )
    if existing.confirmed:
        raise ApiError(409, "invalid_state", "هذا الموعد مؤكَّد بالفعل")
    if existing.responsible_user_id != user.id and user.role != MANAGER:
        raise ApiError(
            403,
            "forbidden",
            "يجب أن تكون المحامي المسؤول عن الموعد لتتمكن من تأكيده",
        )

    now = datetime.now(timezone.utc)
    row = await conn.fetchrow(
        f"""
        UPDATE deadlines
        SET confirmed = true, confirmed_by = $2, confirmed_at = $3, updated_at = now()
        WHERE id = $1
        RETURNING {_DEADLINE_COLS}
        """,
        deadline_id,
        user.id,
        now,
    )
    if row is None:
        raise ApiError(404, "not_found", "الموعد غير موجود")
    logger.info(
        "deadline confirmed: id=%s type=%s by user=%s",
        deadline_id, existing.type, user.id,
    )
    return _row(row)


# ── POST /deadlines/{id}/acknowledge — lawyer acknowledges reminder ────────────


@router.post("/deadlines/{deadline_id}/acknowledge", response_model=Deadline)
async def acknowledge_deadline(
    deadline_id: UUID, user: CurrentUserDep, conn: Db
) -> Deadline:
    """Record that the responsible lawyer has acknowledged this deadline.

    Acknowledgement resets the escalation clock — the scheduler will not
    escalate to a partner_manager if the deadline is acknowledged.
    """
    existing = await _get_deadline_or_404(conn, deadline_id)
    await assert_case_access(conn, user, existing.case_id)

    if existing.responsible_user_id != user.id and user.role != MANAGER:
        raise ApiError(
            403, "forbidden", "يجب أن تكون المحامي المسؤول لتأكيد الاستلام"
        )

    now = datetime.now(timezone.utc)
    row = await conn.fetchrow(
        f"""
        UPDATE deadlines SET acknowledged_at = $2, updated_at = now()
        WHERE id = $1
        RETURNING {_DEADLINE_COLS}
        """,
        deadline_id,
        now,
    )
    if row is None:
        raise ApiError(404, "not_found", "الموعد غير موجود")
    return _row(row)
