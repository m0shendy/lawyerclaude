"""Correspondence Log endpoints (Module E).

Endpoints
---------
  GET    /cases/{case_id}/correspondence       — chronological list
  POST   /cases/{case_id}/correspondence       — record a communication
  PATCH  /correspondence/{id}                  — update
  DELETE /correspondence/{id}                  — delete
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, PARALEGAL, SECRETARY, assert_case_access, require_roles
from app.core.security import CurrentUser, CurrentUserDep

logger = logging.getLogger(__name__)

router = APIRouter()

Direction = Literal["inbound", "outbound"]
Channel   = Literal["email", "letter", "fax", "whatsapp", "phone", "court", "other"]

_CORR_COLS = (
    "id, case_id, direction, channel, subject, body_summary, "
    "document_id, contact_id, sent_received_at, recorded_by, created_at"
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class CorrespondenceRead(BaseModel):
    id: UUID
    case_id: UUID
    direction: Direction
    channel: Channel
    subject: str
    body_summary: str | None = None
    document_id: UUID | None = None
    contact_id: UUID | None = None
    sent_received_at: str
    recorded_by: UUID | None = None
    created_at: str


class CorrespondenceCreate(BaseModel):
    direction: Direction
    channel: Channel
    subject: str
    body_summary: str | None = None
    document_id: UUID | None = None
    contact_id: UUID | None = None
    sent_received_at: datetime | None = None


class CorrespondenceUpdate(BaseModel):
    direction: Direction | None = None
    channel: Channel | None = None
    subject: str | None = None
    body_summary: str | None = None
    document_id: UUID | None = None
    contact_id: UUID | None = None
    sent_received_at: datetime | None = None


def _row(r) -> CorrespondenceRead:
    d = dict(r)
    d["sent_received_at"] = d["sent_received_at"].isoformat()
    d["created_at"] = d["created_at"].isoformat()
    return CorrespondenceRead(**d)


async def _get_or_404(conn, corr_id: UUID) -> CorrespondenceRead:
    r = await conn.fetchrow(f"SELECT {_CORR_COLS} FROM correspondence WHERE id=$1", corr_id)
    if r is None:
        raise ApiError(404, "not_found", "المراسلة غير موجودة")
    return _row(r)


# ── GET /cases/{case_id}/correspondence ──────────────────────────────────────

@router.get("/cases/{case_id}/correspondence", response_model=list[CorrespondenceRead])
async def list_correspondence(case_id: UUID, user: CurrentUserDep, conn: Db) -> list[CorrespondenceRead]:
    await assert_case_access(conn, user, case_id)
    rows = await conn.fetch(
        f"SELECT {_CORR_COLS} FROM correspondence WHERE case_id=$1 ORDER BY sent_received_at DESC",
        case_id,
    )
    return [_row(r) for r in rows]


# ── POST /cases/{case_id}/correspondence ─────────────────────────────────────

@router.post("/cases/{case_id}/correspondence", response_model=CorrespondenceRead, status_code=201)
async def create_correspondence(
    case_id: UUID,
    body: CorrespondenceCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL, SECRETARY))],
) -> CorrespondenceRead:
    await assert_case_access(conn, user, case_id)
    r = await conn.fetchrow(
        f"""
        INSERT INTO correspondence
          (case_id, direction, channel, subject, body_summary,
           document_id, contact_id, sent_received_at, recorded_by)
        VALUES ($1,$2,$3,$4,$5,$6,$7,coalesce($8, now()),$9)
        RETURNING {_CORR_COLS}
        """,
        case_id, body.direction, body.channel, body.subject, body.body_summary,
        body.document_id, body.contact_id, body.sent_received_at, user.id,
    )
    return _row(r)


# ── PATCH /correspondence/{id} ────────────────────────────────────────────────

@router.patch("/correspondence/{corr_id}", response_model=CorrespondenceRead)
async def update_correspondence(
    corr_id: UUID,
    body: CorrespondenceUpdate,
    user: CurrentUserDep,
    conn: Db,
) -> CorrespondenceRead:
    existing = await _get_or_404(conn, corr_id)
    await assert_case_access(conn, user, existing.case_id)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return existing

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(corr_id)

    r = await conn.fetchrow(
        f"UPDATE correspondence SET {', '.join(parts)} WHERE id=${len(params)} RETURNING {_CORR_COLS}",
        *params,
    )
    return _row(r)


# ── DELETE /correspondence/{id} ───────────────────────────────────────────────

@router.delete("/correspondence/{corr_id}", status_code=200)
async def delete_correspondence(corr_id: UUID, user: CurrentUserDep, conn: Db) -> dict:
    existing = await _get_or_404(conn, corr_id)
    await assert_case_access(conn, user, existing.case_id)

    await conn.execute("DELETE FROM correspondence WHERE id=$1", corr_id)
    return {"status": "deleted", "id": str(corr_id)}
