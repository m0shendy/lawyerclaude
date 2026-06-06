"""Client Portal endpoints (Module G).

No staff JWT required — clients authenticate via time-limited magic links.
The portal API uses the service_role DB connection (bypasses RLS) since
portal clients are not Supabase Auth users.

Endpoints
---------
  POST   /portal/auth/request-link    — send magic link to phone/email
  POST   /portal/auth/verify          — verify token → portal session JWT

  GET    /portal/cases                — cases where contact is a client
  GET    /portal/cases/{id}           — case summary + hearings + tasks
  GET    /portal/documents            — portal_visible docs for client's cases
  GET    /portal/invoices             — invoices linked to client contact
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from app.core.db import db_connection
from app.core.errors import ApiError
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["portal"])


# ── Portal session JWT (simple, separate from staff JWT) ─────────────────────
# Uses a signed token distinct from staff tokens to prevent privilege escalation.
# The portal_access_id is embedded as the subject.

def _create_portal_token(portal_access_id: UUID) -> str:
    import jwt, time
    settings = get_settings()
    secret = settings.gotrue_jwt_secret  # reuse same secret; type claim separates portal from staff
    payload = {
        "sub": str(portal_access_id),
        "type": "portal",
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400 * 7,  # 7-day session
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _decode_portal_token(token: str) -> UUID:
    import jwt
    settings = get_settings()
    secret = settings.gotrue_jwt_secret
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        if payload.get("type") != "portal":
            raise ApiError(401, "unauthorized", "رمز الدخول غير صالح")
        return UUID(payload["sub"])
    except ApiError:
        raise
    except Exception:
        raise ApiError(401, "unauthorized", "رمز الدخول غير صالح أو منتهي الصلاحية")


async def get_portal_access_id(authorization: str = Header(...)) -> UUID:
    if not authorization.startswith("Bearer "):
        raise ApiError(401, "unauthorized", "يجب تقديم رمز الدخول")
    return _decode_portal_token(authorization.removeprefix("Bearer ").strip())


PortalUser = UUID  # portal_access_id


# ── Auth endpoints ────────────────────────────────────────────────────────────

class RequestLinkBody(BaseModel):
    phone: str | None = None
    email: str | None = None


class VerifyBody(BaseModel):
    token: str


class VerifyResponse(BaseModel):
    access_token: str
    portal_access_id: str
    contact_id: str


@router.post("/auth/request-link", status_code=200)
async def request_magic_link(body: RequestLinkBody) -> dict:
    """Generate a magic link and send via WhatsApp (phone) or email."""
    if not body.phone and not body.email:
        raise ApiError(400, "bad_request", "يجب تقديم رقم الهاتف أو البريد الإلكتروني")

    async with db_connection(user=None, context="portal:request-link") as conn:
        # Find portal_access by phone or email
        if body.phone:
            pa = await conn.fetchrow(
                "SELECT id, is_active FROM portal_access WHERE phone=$1", body.phone
            )
        else:
            pa = await conn.fetchrow(
                "SELECT id, is_active FROM portal_access WHERE email=$1", body.email
            )

        if pa is None or not pa["is_active"]:
            # Return 200 regardless to avoid user enumeration
            return {"message": "إذا كان الحساب موجوداً، سيتم إرسال رابط الدخول"}

        pa_id = pa["id"]
        # Expire old unused links
        await conn.execute(
            """
            UPDATE portal_magic_links
            SET expires_at = now()
            WHERE portal_access_id = $1 AND used_at IS NULL AND expires_at > now()
            """,
            pa_id,
        )
        # Create new link
        link_row = await conn.fetchrow(
            """
            INSERT INTO portal_magic_links (portal_access_id)
            VALUES ($1) RETURNING token, expires_at
            """,
            pa_id,
        )
        token = link_row["token"]

    # TODO: send via WAHA (WhatsApp) or email. For now just return the token
    # in dev mode — production should send it out-of-band.
    logger.info("Portal magic link generated for portal_access_id=%s", pa_id)
    # In production: do NOT return the token. Send it to phone/email instead.
    return {"message": "إذا كان الحساب موجوداً، سيتم إرسال رابط الدخول",
            "_dev_token": token}  # remove in production


@router.post("/auth/verify", response_model=VerifyResponse)
async def verify_magic_link(body: VerifyBody) -> VerifyResponse:
    async with db_connection(user=None, context="portal:verify") as conn:
        link = await conn.fetchrow(
            """
            SELECT ml.id, ml.portal_access_id, ml.expires_at, ml.used_at, pa.contact_id, pa.is_active
            FROM portal_magic_links ml
            JOIN portal_access pa ON ml.portal_access_id = pa.id
            WHERE ml.token = $1
            """,
            body.token,
        )
        if link is None:
            raise ApiError(401, "unauthorized", "الرابط غير صالح")
        if link["used_at"] is not None:
            raise ApiError(401, "unauthorized", "الرابط مستخدم بالفعل")
        if link["expires_at"] < datetime.now(tz=timezone.utc):
            raise ApiError(401, "unauthorized", "الرابط منتهي الصلاحية")
        if not link["is_active"]:
            raise ApiError(401, "unauthorized", "الحساب غير نشط")

        pa_id = link["portal_access_id"]
        contact_id = link["contact_id"]

        # Mark link as used and update last_login
        await conn.execute(
            "UPDATE portal_magic_links SET used_at=now() WHERE id=$1", link["id"]
        )
        await conn.execute(
            "UPDATE portal_access SET last_login_at=now() WHERE id=$1", pa_id
        )

    access_token = _create_portal_token(pa_id)
    return VerifyResponse(
        access_token=access_token,
        portal_access_id=str(pa_id),
        contact_id=str(contact_id),
    )


# ── Portal data endpoints ─────────────────────────────────────────────────────

class PortalCaseSummary(BaseModel):
    case_id: UUID
    title: str
    case_number: str | None
    court: str | None
    status: str
    created_at: str


class PortalCaseDetail(PortalCaseSummary):
    hearings: list[dict]
    tasks: list[dict]


class PortalDocument(BaseModel):
    id: UUID
    case_id: UUID
    file_name: str
    file_path: str
    created_at: str


class PortalInvoice(BaseModel):
    id: UUID
    invoice_number: str
    issue_date: str
    due_date: str
    status: str
    total_egp: str
    amount_paid: str


async def _get_contact_for_portal(conn, pa_id: UUID) -> UUID:
    contact_id = await conn.fetchval(
        "SELECT contact_id FROM portal_access WHERE id=$1 AND is_active=true", pa_id
    )
    if contact_id is None:
        raise ApiError(401, "unauthorized", "الحساب غير نشط")
    return contact_id


@router.get("/cases", response_model=list[PortalCaseSummary])
async def portal_cases(pa_id: UUID = Depends(get_portal_access_id)) -> list[PortalCaseSummary]:
    async with db_connection(user=None, context="portal:cases") as conn:
        contact_id = await _get_contact_for_portal(conn, pa_id)
        rows = await conn.fetch(
            """
            SELECT c.id AS case_id, c.title, c.case_number, c.court, c.status, c.created_at
            FROM cases c
            JOIN case_contacts cc ON cc.case_id = c.id
            WHERE cc.contact_id = $1 AND cc.role = 'client'
            ORDER BY c.created_at DESC
            """,
            contact_id,
        )
        return [
            PortalCaseSummary(
                case_id=r["case_id"], title=r["title"], case_number=r["case_number"],
                court=r["court"], status=r["status"],
                created_at=r["created_at"].isoformat(),
            )
            for r in rows
        ]


@router.get("/cases/{case_id}", response_model=PortalCaseDetail)
async def portal_case_detail(
    case_id: UUID,
    pa_id: UUID = Depends(get_portal_access_id),
) -> PortalCaseDetail:
    async with db_connection(user=None, context="portal:case-detail") as conn:
        contact_id = await _get_contact_for_portal(conn, pa_id)

        # Verify the contact is linked to this case as client
        is_client = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM case_contacts WHERE case_id=$1 AND contact_id=$2 AND role='client')",
            case_id, contact_id,
        )
        if not is_client:
            raise ApiError(404, "not_found", "القضية غير موجودة")

        case_row = await conn.fetchrow(
            "SELECT id AS case_id, title, case_number, court, status, created_at FROM cases WHERE id=$1",
            case_id,
        )
        if case_row is None:
            raise ApiError(404, "not_found", "القضية غير موجودة")

        hearing_rows = await conn.fetch(
            """
            SELECT id, hearing_date, court_name, status, result, next_hearing_date
            FROM hearings WHERE case_id=$1 ORDER BY hearing_date DESC LIMIT 10
            """,
            case_id,
        )
        task_rows = await conn.fetch(
            "SELECT id, description, due_date, status FROM tasks WHERE case_id=$1 ORDER BY due_date",
            case_id,
        )

        hearings = [
            {"id": str(r["id"]), "hearing_date": r["hearing_date"].isoformat(),
             "court_name": r["court_name"], "status": r["status"],
             "result": r["result"],
             "next_hearing_date": r["next_hearing_date"].isoformat() if r["next_hearing_date"] else None}
            for r in hearing_rows
        ]
        tasks = [
            {"id": str(r["id"]), "description": r["description"],
             "due_date": r["due_date"].isoformat() if r["due_date"] else None,
             "status": r["status"]}
            for r in task_rows
        ]

        return PortalCaseDetail(
            case_id=case_row["case_id"],
            title=case_row["title"],
            case_number=case_row["case_number"],
            court=case_row["court"],
            status=case_row["status"],
            created_at=case_row["created_at"].isoformat(),
            hearings=hearings,
            tasks=tasks,
        )


@router.get("/documents", response_model=list[PortalDocument])
async def portal_documents(pa_id: UUID = Depends(get_portal_access_id)) -> list[PortalDocument]:
    async with db_connection(user=None, context="portal:documents") as conn:
        contact_id = await _get_contact_for_portal(conn, pa_id)
        rows = await conn.fetch(
            """
            SELECT d.id, d.case_id, d.file_name, d.file_path, d.created_at
            FROM documents d
            JOIN case_contacts cc ON cc.case_id = d.case_id
            WHERE cc.contact_id = $1
              AND cc.role = 'client'
              AND d.portal_visible = true
            ORDER BY d.created_at DESC
            """,
            contact_id,
        )
        return [
            PortalDocument(
                id=r["id"], case_id=r["case_id"], file_name=r["file_name"],
                file_path=r["file_path"], created_at=r["created_at"].isoformat(),
            )
            for r in rows
        ]


@router.get("/invoices", response_model=list[PortalInvoice])
async def portal_invoices(pa_id: UUID = Depends(get_portal_access_id)) -> list[PortalInvoice]:
    async with db_connection(user=None, context="portal:invoices") as conn:
        contact_id = await _get_contact_for_portal(conn, pa_id)
        rows = await conn.fetch(
            """
            SELECT
                i.id, i.invoice_number, i.issue_date, i.due_date,
                i.status, i.total_egp,
                coalesce(sum(p.amount_egp), 0) AS amount_paid
            FROM invoices i
            LEFT JOIN payments p ON p.invoice_id = i.id
            WHERE i.contact_id = $1
              AND i.status NOT IN ('draft','cancelled')
            GROUP BY i.id
            ORDER BY i.issue_date DESC
            """,
            contact_id,
        )
        return [
            PortalInvoice(
                id=r["id"], invoice_number=r["invoice_number"],
                issue_date=r["issue_date"].isoformat(),
                due_date=r["due_date"].isoformat(),
                status=r["status"],
                total_egp=str(r["total_egp"]),
                amount_paid=str(r["amount_paid"]),
            )
            for r in rows
        ]
