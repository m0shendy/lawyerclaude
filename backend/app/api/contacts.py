"""Contacts & Parties registry endpoints (Module A).

Endpoints
---------
  GET    /contacts              — searchable list with type filter
  POST   /contacts              — create contact
  GET    /contacts/{id}         — detail + linked cases
  PATCH  /contacts/{id}         — update
  DELETE /contacts/{id}         — soft-delete (is_active=false)

  GET    /cases/{case_id}/contacts          — parties linked to a case
  POST   /cases/{case_id}/contacts          — link (or create+link) a contact
  DELETE /cases/{case_id}/contacts/{link_id} — unlink (removes case_contacts row)

All mutations go through the audited DB connection. [C-III]
"""

from __future__ import annotations

import logging
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

ContactType = Literal[
    "client", "opposing_party", "opposing_counsel",
    "court", "judge", "notary", "government", "expert", "other"
]
ContactCaseRole = Literal[
    "client", "opposing_party", "opposing_counsel",
    "witness", "expert", "court", "other"
]

_CONTACT_COLS = (
    "id, type, name_ar, name_en, national_id, tax_id, "
    "phone, email, address, notes, is_active, created_by, created_at, updated_at"
)
_LINK_COLS = "id, case_id, contact_id, role, notes, added_at"


# ── Pydantic models ───────────────────────────────────────────────────────────

class ContactRead(BaseModel):
    id: UUID
    type: ContactType
    name_ar: str
    name_en: str | None = None
    national_id: str | None = None
    tax_id: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    notes: str | None = None
    is_active: bool
    created_by: UUID | None = None
    created_at: str
    updated_at: str


class ContactCreate(BaseModel):
    type: ContactType
    name_ar: str
    name_en: str | None = None
    national_id: str | None = None
    tax_id: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    notes: str | None = None


class ContactUpdate(BaseModel):
    type: ContactType | None = None
    name_ar: str | None = None
    name_en: str | None = None
    national_id: str | None = None
    tax_id: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class CaseContactLink(BaseModel):
    id: UUID
    case_id: UUID
    contact_id: UUID
    role: ContactCaseRole
    notes: str | None = None
    added_at: str


class CaseContactWithDetail(CaseContactLink):
    name_ar: str
    name_en: str | None = None
    type: ContactType
    phone: str | None = None


class LinkContactRequest(BaseModel):
    """Link an existing contact to a case, or create+link in one call."""
    contact_id: UUID | None = None         # if None, create_data must be provided
    create_data: ContactCreate | None = None
    role: ContactCaseRole
    notes: str | None = None


def _row_to_contact(r) -> ContactRead:
    d = dict(r)
    d["created_at"] = d["created_at"].isoformat()
    d["updated_at"] = d["updated_at"].isoformat()
    return ContactRead(**d)


def _row_to_link(r) -> CaseContactLink:
    d = dict(r)
    d["added_at"] = d["added_at"].isoformat()
    return CaseContactLink(**d)


async def _get_contact_or_404(conn, contact_id: UUID) -> ContactRead:
    row = await conn.fetchrow(
        f"SELECT {_CONTACT_COLS} FROM contacts WHERE id = $1", contact_id
    )
    if row is None:
        raise ApiError(404, "not_found", "جهة الاتصال غير موجودة")
    return _row_to_contact(row)


# ── GET /contacts ─────────────────────────────────────────────────────────────

@router.get("/contacts", response_model=list[ContactRead])
async def list_contacts(
    user: CurrentUserDep,
    conn: Db,
    type: ContactType | None = Query(None),
    search: str | None = Query(None),
    include_inactive: bool = Query(False),
) -> list[ContactRead]:
    conditions = []
    params: list = []

    if not include_inactive:
        conditions.append("is_active = true")

    if type is not None:
        params.append(type)
        conditions.append(f"type = ${len(params)}")

    if search:
        params.append(search)
        conditions.append(
            f"(name_ar ILIKE '%' || ${len(params)} || '%' "
            f"OR name_en ILIKE '%' || ${len(params)} || '%' "
            f"OR phone ILIKE '%' || ${len(params)} || '%')"
        )

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await conn.fetch(
        f"SELECT {_CONTACT_COLS} FROM contacts {where} ORDER BY name_ar LIMIT 500",
        *params,
    )
    return [_row_to_contact(r) for r in rows]


# ── POST /contacts ────────────────────────────────────────────────────────────

@router.post("/contacts", response_model=ContactRead, status_code=201)
async def create_contact(
    body: ContactCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL, SECRETARY))],
) -> ContactRead:
    row = await conn.fetchrow(
        f"""
        INSERT INTO contacts
          (type, name_ar, name_en, national_id, tax_id, phone, email, address, notes, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING {_CONTACT_COLS}
        """,
        body.type, body.name_ar, body.name_en, body.national_id, body.tax_id,
        body.phone, body.email, body.address, body.notes, user.id,
    )
    return _row_to_contact(row)


# ── GET /contacts/{id} ────────────────────────────────────────────────────────

class ContactDetail(ContactRead):
    cases: list[dict]  # [{case_id, title, case_number, role}]


@router.get("/contacts/{contact_id}", response_model=ContactDetail)
async def get_contact(contact_id: UUID, user: CurrentUserDep, conn: Db) -> ContactDetail:
    contact = await _get_contact_or_404(conn, contact_id)
    linked_cases = await conn.fetch(
        """
        SELECT cc.case_id, c.title, c.case_number, cc.role
        FROM case_contacts cc
        JOIN cases c ON cc.case_id = c.id
        WHERE cc.contact_id = $1
        ORDER BY c.created_at DESC
        LIMIT 50
        """,
        contact_id,
    )
    cases_list = [
        {"case_id": str(r["case_id"]), "title": r["title"],
         "case_number": r["case_number"], "role": r["role"]}
        for r in linked_cases
    ]
    return ContactDetail(**contact.model_dump(), cases=cases_list)


# ── PATCH /contacts/{id} ─────────────────────────────────────────────────────

@router.patch("/contacts/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: UUID,
    body: ContactUpdate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL, SECRETARY))],
) -> ContactRead:
    await _get_contact_or_404(conn, contact_id)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return await _get_contact_or_404(conn, contact_id)

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(contact_id)

    row = await conn.fetchrow(
        f"""
        UPDATE contacts SET {", ".join(parts)}, updated_at = now()
        WHERE id = ${len(params)}
        RETURNING {_CONTACT_COLS}
        """,
        *params,
    )
    return _row_to_contact(row)


# ── DELETE /contacts/{id} ─────────────────────────────────────────────────────
# Soft-delete (default): sets is_active=false.
# Hard delete (?hard=true): manager only, permanent removal.

@router.delete("/contacts/{contact_id}", status_code=200)
async def delete_contact(
    contact_id: UUID,
    user: CurrentUserDep,
    conn: Db,
    hard: bool = Query(False, description="إذا كانت true يتم الحذف النهائي (مدير فقط)"),
) -> dict:
    await _get_contact_or_404(conn, contact_id)
    if hard:
        if user.role != MANAGER:
            raise ApiError(403, "forbidden", "الحذف النهائي يتطلب صلاحيات مدير")
        await conn.execute("DELETE FROM contacts WHERE id = $1", contact_id)
        return {"status": "deleted", "id": str(contact_id)}
    # Soft delete — preserve the record, just mark inactive
    await conn.execute(
        "UPDATE contacts SET is_active = false, updated_at = now() WHERE id = $1",
        contact_id,
    )
    return {"status": "deactivated", "id": str(contact_id)}


# ── GET /cases/{case_id}/contacts ─────────────────────────────────────────────

@router.get("/cases/{case_id}/contacts", response_model=list[CaseContactWithDetail])
async def list_case_contacts(case_id: UUID, user: CurrentUserDep, conn: Db) -> list[CaseContactWithDetail]:
    await assert_case_access(conn, user, case_id)
    rows = await conn.fetch(
        """
        SELECT cc.id, cc.case_id, cc.contact_id, cc.role, cc.notes, cc.added_at,
               c.name_ar, c.name_en, c.type, c.phone
        FROM case_contacts cc
        JOIN contacts c ON cc.contact_id = c.id
        WHERE cc.case_id = $1
        ORDER BY cc.added_at
        """,
        case_id,
    )
    result = []
    for r in rows:
        d = dict(r)
        d["added_at"] = d["added_at"].isoformat()
        result.append(CaseContactWithDetail(**d))
    return result


# ── POST /cases/{case_id}/contacts ────────────────────────────────────────────

@router.post("/cases/{case_id}/contacts", response_model=CaseContactLink, status_code=201)
async def link_contact_to_case(
    case_id: UUID,
    body: LinkContactRequest,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL, SECRETARY))],
) -> CaseContactLink:
    await assert_case_access(conn, user, case_id)

    contact_id = body.contact_id
    if contact_id is None:
        if body.create_data is None:
            raise ApiError(400, "bad_request", "يجب تقديم contact_id أو create_data")
        new_contact = await conn.fetchrow(
            f"""
            INSERT INTO contacts
              (type, name_ar, name_en, national_id, tax_id, phone, email, address, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING id
            """,
            body.create_data.type, body.create_data.name_ar, body.create_data.name_en,
            body.create_data.national_id, body.create_data.tax_id, body.create_data.phone,
            body.create_data.email, body.create_data.address, body.create_data.notes,
            user.id,
        )
        contact_id = new_contact["id"]
    else:
        await _get_contact_or_404(conn, contact_id)

    # Check for duplicate link
    existing_link = await conn.fetchval(
        "SELECT id FROM case_contacts WHERE case_id=$1 AND contact_id=$2 AND role=$3",
        case_id, contact_id, body.role,
    )
    if existing_link:
        raise ApiError(409, "conflict", "هذا الارتباط موجود بالفعل")

    row = await conn.fetchrow(
        f"""
        INSERT INTO case_contacts (case_id, contact_id, role, notes)
        VALUES ($1, $2, $3, $4)
        RETURNING {_LINK_COLS}
        """,
        case_id, contact_id, body.role, body.notes,
    )
    return _row_to_link(row)


# ── DELETE /cases/{case_id}/contacts/{link_id} ────────────────────────────────

@router.delete("/cases/{case_id}/contacts/{link_id}", status_code=200)
async def unlink_contact_from_case(
    case_id: UUID,
    link_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL))],
) -> dict:
    await assert_case_access(conn, user, case_id)
    deleted = await conn.fetchval(
        "DELETE FROM case_contacts WHERE id = $1 AND case_id = $2 RETURNING id",
        link_id, case_id,
    )
    if deleted is None:
        raise ApiError(404, "not_found", "الارتباط غير موجود")
    return {"status": "unlinked", "id": str(deleted)}
