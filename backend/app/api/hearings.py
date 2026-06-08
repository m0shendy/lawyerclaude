"""Court Hearings endpoints (Module C).

Endpoints
---------
  GET    /cases/{case_id}/hearings    — list hearings for a case
  POST   /cases/{case_id}/hearings    — schedule a hearing
  PATCH  /hearings/{id}               — update outcome / next date
  DELETE /hearings/{id}               — cancel/delete
  GET    /hearings/upcoming            — cross-case calendar (?days=30)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, PARALEGAL, SECRETARY, assert_case_access, require_roles
from app.core.security import CurrentUser, CurrentUserDep

logger = logging.getLogger(__name__)

router = APIRouter()

HearingStatus = Literal["scheduled", "held", "adjourned", "cancelled"]

_HEARING_COLS = (
    "id, case_id, hearing_date, court_name, court_room, judge_contact_id, "
    "assigned_lawyer_id, status, result, next_hearing_date, next_hearing_court, "
    "notes, reminder_sent_7d, reminder_sent_3d, reminder_sent_1d, reminder_sent_0d, "
    "created_by, created_at, updated_at"
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class HearingRead(BaseModel):
    id: UUID
    case_id: UUID
    hearing_date: str
    court_name: str
    court_room: str | None = None
    judge_contact_id: UUID | None = None
    assigned_lawyer_id: UUID | None = None
    status: HearingStatus
    result: str | None = None
    next_hearing_date: str | None = None
    next_hearing_court: str | None = None
    notes: str | None = None
    reminder_sent_7d: bool
    reminder_sent_3d: bool
    reminder_sent_1d: bool
    reminder_sent_0d: bool
    created_by: UUID | None = None
    created_at: str
    updated_at: str


class HearingCreate(BaseModel):
    hearing_date: datetime
    court_name: str
    court_room: str | None = None
    judge_contact_id: UUID | None = None
    assigned_lawyer_id: UUID | None = None
    notes: str | None = None


class HearingUpdate(BaseModel):
    hearing_date: datetime | None = None
    court_name: str | None = None
    court_room: str | None = None
    judge_contact_id: UUID | None = None
    assigned_lawyer_id: UUID | None = None
    status: HearingStatus | None = None
    result: str | None = None
    next_hearing_date: datetime | None = None
    next_hearing_court: str | None = None
    notes: str | None = None


class HearingWithCase(HearingRead):
    case_title: str
    case_number: str | None = None


def _row(r) -> HearingRead:
    d = dict(r)
    d["hearing_date"] = d["hearing_date"].isoformat()
    d["created_at"] = d["created_at"].isoformat()
    d["updated_at"] = d["updated_at"].isoformat()
    if d.get("next_hearing_date"):
        d["next_hearing_date"] = d["next_hearing_date"].isoformat()
    return HearingRead(**d)


async def _get_hearing_or_404(conn, hearing_id: UUID) -> HearingRead:
    r = await conn.fetchrow(f"SELECT {_HEARING_COLS} FROM hearings WHERE id=$1", hearing_id)
    if r is None:
        raise ApiError(404, "not_found", "الجلسة غير موجودة")
    return _row(r)


# ── GET /cases/{case_id}/hearings ─────────────────────────────────────────────

@router.get("/cases/{case_id}/hearings", response_model=list[HearingRead])
async def list_case_hearings(case_id: UUID, user: CurrentUserDep, conn: Db) -> list[HearingRead]:
    await assert_case_access(conn, user, case_id)
    rows = await conn.fetch(
        f"SELECT {_HEARING_COLS} FROM hearings WHERE case_id=$1 ORDER BY hearing_date DESC",
        case_id,
    )
    return [_row(r) for r in rows]


# ── POST /cases/{case_id}/hearings ────────────────────────────────────────────

@router.post("/cases/{case_id}/hearings", response_model=HearingRead, status_code=201)
async def create_hearing(
    case_id: UUID,
    body: HearingCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL, SECRETARY))],
) -> HearingRead:
    await assert_case_access(conn, user, case_id)

    r = await conn.fetchrow(
        f"""
        INSERT INTO hearings
          (case_id, hearing_date, court_name, court_room, judge_contact_id,
           assigned_lawyer_id, notes, created_by)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        RETURNING {_HEARING_COLS}
        """,
        case_id, body.hearing_date, body.court_name, body.court_room,
        body.judge_contact_id, body.assigned_lawyer_id, body.notes, user.id,
    )
    return _row(r)


# ── PATCH /hearings/{id} ──────────────────────────────────────────────────────

@router.patch("/hearings/{hearing_id}", response_model=HearingRead)
async def update_hearing(
    hearing_id: UUID,
    body: HearingUpdate,
    user: CurrentUserDep,
    conn: Db,
) -> HearingRead:
    existing = await _get_hearing_or_404(conn, hearing_id)
    await assert_case_access(conn, user, existing.case_id)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return existing

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(hearing_id)

    r = await conn.fetchrow(
        f"UPDATE hearings SET {', '.join(parts)}, updated_at=now() WHERE id=${len(params)} RETURNING {_HEARING_COLS}",
        *params,
    )
    return _row(r)


# ── DELETE /hearings/{id} ─────────────────────────────────────────────────────

@router.delete("/hearings/{hearing_id}", status_code=200)
async def delete_hearing(hearing_id: UUID, user: CurrentUserDep, conn: Db) -> dict:
    existing = await _get_hearing_or_404(conn, hearing_id)
    await assert_case_access(conn, user, existing.case_id)

    if user.role != MANAGER and existing.status == "held":
        raise ApiError(403, "forbidden", "لا يمكن حذف جلسة منعقدة — استخدم التحديث للإلغاء")

    await conn.execute("DELETE FROM hearings WHERE id=$1", hearing_id)
    return {"status": "deleted", "id": str(hearing_id)}


# ── GET /hearings/upcoming ────────────────────────────────────────────────────
# Note: this route must be declared BEFORE /{hearing_id} to avoid FastAPI
# treating the literal string "upcoming" as a UUID path parameter.

@router.get("/hearings/upcoming", response_model=list[HearingWithCase])
async def upcoming_hearings(
    user: CurrentUserDep,
    conn: Db,
    days: int = Query(30, ge=1, le=365),
) -> list[HearingWithCase]:
    cutoff = datetime.now(tz=timezone.utc) + timedelta(days=days)
    rows = await conn.fetch(
        f"""
        SELECT h.{', h.'.join(_HEARING_COLS.split(', '))},
               c.title AS case_title, c.case_number
        FROM hearings h
        JOIN cases c ON h.case_id = c.id
        WHERE h.status = 'scheduled'
          AND h.hearing_date >= now()
          AND h.hearing_date <= $1
        ORDER BY h.hearing_date ASC
        LIMIT 200
        """,
        cutoff,
    )
    result = []
    for r in rows:
        d = dict(r)
        d["hearing_date"] = d["hearing_date"].isoformat()
        d["created_at"] = d["created_at"].isoformat()
        d["updated_at"] = d["updated_at"].isoformat()
        if d.get("next_hearing_date"):
            d["next_hearing_date"] = d["next_hearing_date"].isoformat()
        result.append(HearingWithCase(**d))
    return result


# ── GET /hearings/{id} ────────────────────────────────────────────────────────
# Declared AFTER /hearings/upcoming so "upcoming" is matched by the literal
# route, not captured as a UUID path parameter.

@router.get("/hearings/{hearing_id}", response_model=HearingRead)
async def get_hearing(hearing_id: UUID, user: CurrentUserDep, conn: Db) -> HearingRead:
    existing = await _get_hearing_or_404(conn, hearing_id)
    await assert_case_access(conn, user, existing.case_id)
    return existing
