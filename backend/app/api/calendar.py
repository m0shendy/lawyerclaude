"""Unified calendar endpoint (spec 002 US8).

GET /calendar — reads the ``calendar_events`` view (hearings ∪ appointments)
with date-range, type, and lawyer filters. Pure read; assembly is the DB view,
never an LLM [C-IV]. RLS applies through the security-invoker view.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.db import Db
from app.core.rbac import MANAGER
from app.core.security import CurrentUserDep

logger = logging.getLogger(__name__)

router = APIRouter()

EventType = Literal["hearing", "appointment"]


class CalendarEvent(BaseModel):
    id: UUID
    event_type: EventType
    title: str
    starts_at: datetime
    ends_at: datetime
    case_id: UUID | None = None
    assigned_lawyer_id: UUID | None = None
    status: str


@router.get("/calendar", response_model=list[CalendarEvent])
async def get_calendar(
    user: CurrentUserDep,
    conn: Db,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    type: Annotated[Literal["all", "hearing", "appointment"], Query()] = "all",
    lawyer_id: Annotated[UUID | None, Query()] = None,
) -> list[CalendarEvent]:
    params: list = []
    where: list[str] = []

    def _add(clause: str, value) -> None:
        params.append(value)
        where.append(clause.format(n=len(params)))

    if from_date is not None:
        _add("starts_at >= ${n}", from_date)
    if to_date is not None:
        _add("starts_at < ${n}::date + 1", to_date)
    if type != "all":
        _add("event_type = ${n}", type)
    if lawyer_id is not None:
        _add("assigned_lawyer_id = ${n}", lawyer_id)

    if user.role != MANAGER:
        # Non-managers: own events or events on their assigned cases.
        params.append(user.id)
        where.append(
            f"(assigned_lawyer_id = ${len(params)} "
            f"or (case_id is not null and exists ("
            f"select 1 from case_assignments ca "
            f"where ca.case_id = calendar_events.case_id "
            f"and ca.user_id = ${len(params)})))"
        )

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = await conn.fetch(
        f"""
        SELECT id, event_type, title, starts_at, ends_at,
               case_id, assigned_lawyer_id, status
        FROM calendar_events {where_sql}
        ORDER BY starts_at ASC
        """,
        *params,
    )
    return [CalendarEvent(**dict(r)) for r in rows]
