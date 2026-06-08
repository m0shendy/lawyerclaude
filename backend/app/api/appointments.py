"""Appointment scheduling endpoints (spec 002 US7).

  GET    /appointments        — filtered list
  POST   /appointments        — create (409 on lawyer double-booking)
  GET    /appointments/{id}   — detail
  PATCH  /appointments/{id}   — update (re-runs conflict detection)
  DELETE /appointments/{id}   — delete

Conflict detection (FR-129): tstzrange overlap against the same lawyer's
active appointments at the API layer; the DB exclusion constraint
(``no_lawyer_double_booking``) backstops races. All mutations are
audit-logged by DB triggers [C-III].
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, PARALEGAL, SECRETARY, require_roles
from app.core.security import CurrentUser, CurrentUserDep

logger = logging.getLogger(__name__)

router = APIRouter()

AppointmentType = Literal["consultation", "follow_up", "checkup", "emergency"]
AppointmentStatus = Literal[
    "scheduled", "confirmed", "in_progress", "completed", "cancelled"
]

_COLS = (
    "id, type, case_id, contact_id, assigned_lawyer_id, scheduled_at, "
    "duration_minutes, status, reason, notes, created_by, created_at, updated_at"
)


class Appointment(BaseModel):
    id: UUID
    type: AppointmentType
    case_id: UUID | None = None
    contact_id: UUID | None = None
    assigned_lawyer_id: UUID
    scheduled_at: datetime
    duration_minutes: int
    status: AppointmentStatus
    reason: str | None = None
    notes: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AppointmentCreate(BaseModel):
    type: AppointmentType = "consultation"
    case_id: UUID | None = None
    contact_id: UUID | None = None
    assigned_lawyer_id: UUID
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, gt=0)
    reason: str | None = None
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    type: AppointmentType | None = None
    case_id: UUID | None = None
    contact_id: UUID | None = None
    assigned_lawyer_id: UUID | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    status: AppointmentStatus | None = None
    reason: str | None = None
    notes: str | None = None


async def _assert_no_conflict(
    conn,
    *,
    lawyer_id: UUID,
    scheduled_at: datetime,
    duration_minutes: int,
    exclude_id: UUID | None = None,
) -> None:
    """409 if the lawyer already has an active overlapping appointment."""
    clash = await conn.fetchrow(
        """
        SELECT id, scheduled_at, duration_minutes FROM appointments
        WHERE assigned_lawyer_id = $1
          AND status NOT IN ('cancelled', 'completed')
          AND ($4::uuid IS NULL OR id != $4)
          AND tstzrange(scheduled_at,
                        scheduled_at + duration_minutes * interval '1 minute')
              && tstzrange($2::timestamptz,
                           $2::timestamptz + $3 * interval '1 minute')
        LIMIT 1
        """,
        lawyer_id, scheduled_at, duration_minutes, exclude_id,
    )
    if clash:
        raise ApiError(
            409, "appointment_time_conflict",
            "المحامي لديه موعد آخر في نفس التوقيت — اختر وقتًا مختلفًا",
        )


@router.get("/appointments", response_model=list[Appointment])
async def list_appointments(
    user: CurrentUserDep,
    conn: Db,
    lawyer_id: Annotated[UUID | None, Query()] = None,
    case_id: Annotated[UUID | None, Query()] = None,
    contact_id: Annotated[UUID | None, Query()] = None,
    type: Annotated[AppointmentType | None, Query()] = None,
    status: Annotated[AppointmentStatus | None, Query()] = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> list[Appointment]:
    params: list = []
    where: list[str] = []

    def _add(clause: str, value) -> None:
        params.append(value)
        where.append(clause.format(n=len(params)))

    if lawyer_id is not None:
        _add("assigned_lawyer_id = ${n}", lawyer_id)
    if case_id is not None:
        _add("case_id = ${n}", case_id)
    if contact_id is not None:
        _add("contact_id = ${n}", contact_id)
    if type is not None:
        _add("type = ${n}", type)
    if status is not None:
        _add("status = ${n}", status)
    if from_date is not None:
        _add("scheduled_at >= ${n}", from_date)
    if to_date is not None:
        _add("scheduled_at < ${n}::date + 1", to_date)

    if user.role != MANAGER:
        # Visibility: own appointments, ones they created, or on assigned cases.
        params.append(user.id)
        where.append(
            f"(assigned_lawyer_id = ${len(params)} or created_by = ${len(params)} "
            f"or (case_id is not null and exists ("
            f"select 1 from case_assignments ca "
            f"where ca.case_id = appointments.case_id and ca.user_id = ${len(params)})))"
        )

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = await conn.fetch(
        f"SELECT {_COLS} FROM appointments {where_sql} ORDER BY scheduled_at ASC",
        *params,
    )
    return [Appointment(**dict(r)) for r in rows]


@router.post("/appointments", response_model=Appointment, status_code=201)
async def create_appointment(
    body: AppointmentCreate,
    conn: Db,
    user: Annotated[
        CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL, SECRETARY))
    ],
) -> Appointment:
    lawyer = await conn.fetchrow(
        "SELECT id, role, status FROM users WHERE id = $1", body.assigned_lawyer_id
    )
    if lawyer is None:
        raise ApiError(404, "not_found", "المحامي غير موجود")
    if lawyer["status"] != "active":
        raise ApiError(400, "invalid", "لا يمكن تحديد موعد لمستخدم غير نشط")

    await _assert_no_conflict(
        conn,
        lawyer_id=body.assigned_lawyer_id,
        scheduled_at=body.scheduled_at,
        duration_minutes=body.duration_minutes,
    )

    try:
        row = await conn.fetchrow(
            f"""
            INSERT INTO appointments
                (type, case_id, contact_id, assigned_lawyer_id, scheduled_at,
                 duration_minutes, reason, notes, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING {_COLS}
            """,
            body.type, body.case_id, body.contact_id, body.assigned_lawyer_id,
            body.scheduled_at, body.duration_minutes, body.reason, body.notes,
            user.id,
        )
    except Exception as exc:
        # DB exclusion constraint backstop (race with a concurrent insert).
        if "no_lawyer_double_booking" in str(exc):
            raise ApiError(
                409, "appointment_time_conflict",
                "المحامي لديه موعد آخر في نفس التوقيت — اختر وقتًا مختلفًا",
            ) from exc
        raise
    return Appointment(**dict(row))


@router.get("/appointments/{appointment_id}", response_model=Appointment)
async def get_appointment(
    appointment_id: UUID, user: CurrentUserDep, conn: Db
) -> Appointment:
    row = await conn.fetchrow(
        f"SELECT {_COLS} FROM appointments WHERE id = $1", appointment_id
    )
    if row is None:
        raise ApiError(404, "not_found", "الموعد غير موجود")
    return Appointment(**dict(row))


@router.patch("/appointments/{appointment_id}", response_model=Appointment)
async def update_appointment(
    appointment_id: UUID,
    body: AppointmentUpdate,
    conn: Db,
    user: Annotated[
        CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL, SECRETARY))
    ],
) -> Appointment:
    existing = await conn.fetchrow(
        f"SELECT {_COLS} FROM appointments WHERE id = $1", appointment_id
    )
    if existing is None:
        raise ApiError(404, "not_found", "الموعد غير موجود")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return Appointment(**dict(existing))

    # Re-run conflict detection when time/lawyer/duration change and the
    # appointment stays active.
    new_lawyer = updates.get("assigned_lawyer_id", existing["assigned_lawyer_id"])
    new_start = updates.get("scheduled_at", existing["scheduled_at"])
    new_duration = updates.get("duration_minutes", existing["duration_minutes"])
    new_status = updates.get("status", existing["status"])
    if (
        new_status not in ("cancelled", "completed")
        and any(k in updates for k in
                ("assigned_lawyer_id", "scheduled_at", "duration_minutes", "status"))
    ):
        await _assert_no_conflict(
            conn,
            lawyer_id=new_lawyer,
            scheduled_at=new_start,
            duration_minutes=new_duration,
            exclude_id=appointment_id,
        )

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(appointment_id)
    try:
        row = await conn.fetchrow(
            f"""
            UPDATE appointments SET {", ".join(parts)}, updated_at = now()
            WHERE id = ${len(params)}
            RETURNING {_COLS}
            """,
            *params,
        )
    except Exception as exc:
        if "no_lawyer_double_booking" in str(exc):
            raise ApiError(
                409, "appointment_time_conflict",
                "المحامي لديه موعد آخر في نفس التوقيت — اختر وقتًا مختلفًا",
            ) from exc
        raise
    return Appointment(**dict(row))


@router.delete("/appointments/{appointment_id}", status_code=200)
async def delete_appointment(
    appointment_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, SECRETARY))],
) -> dict:
    deleted = await conn.fetchval(
        "DELETE FROM appointments WHERE id = $1 RETURNING id", appointment_id
    )
    if deleted is None:
        raise ApiError(404, "not_found", "الموعد غير موجود")
    return {"status": "deleted", "id": str(deleted)}
