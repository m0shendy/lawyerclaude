"""Billing & Invoicing endpoints (Module B).

Endpoints
---------
Time entries:
  GET    /time-entries           — list (filter: case_id, user_id, from, to)
  POST   /time-entries           — create
  PATCH  /time-entries/{id}      — update
  DELETE /time-entries/{id}      — delete

Invoices:
  GET    /invoices               — list (filter: status, case_id, contact_id)
  POST   /invoices               — create with line items
  GET    /invoices/{id}          — detail with line items and payment history
  PATCH  /invoices/{id}          — update header fields
  POST   /invoices/{id}/send     — draft → sent (triggers WhatsApp notification)
  POST   /invoices/{id}/cancel   — cancel invoice
  GET    /invoices/{id}/pdf      — PDF generation (stub: returns URL)

Payments:
  GET    /invoices/{id}/payments — list payments
  POST   /invoices/{id}/payments — record a payment

Billing rates:
  GET    /billing-rates          — list all rates
  POST   /billing-rates          — set rate for a lawyer
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
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

InvoiceStatus = Literal["draft", "sent", "partial", "paid", "cancelled", "overdue"]
PaymentMethod = Literal["cash", "bank_transfer", "check", "other"]


# ── Pydantic models ───────────────────────────────────────────────────────────

class TimeEntryRead(BaseModel):
    id: UUID
    case_id: UUID
    user_id: UUID
    date: date
    duration_minutes: int
    description: str
    is_billable: bool
    rate_egp: Decimal | None = None
    amount_egp: Decimal | None = None
    invoice_id: UUID | None = None
    created_at: str
    updated_at: str


class TimeEntryCreate(BaseModel):
    case_id: UUID
    entry_date: date
    duration_minutes: int = Field(gt=0)
    description: str = Field(min_length=1)
    is_billable: bool = True
    rate_egp: Decimal | None = None


class TimeEntryUpdate(BaseModel):
    entry_date: date | None = None
    duration_minutes: int | None = None
    description: str | None = None
    is_billable: bool | None = None
    rate_egp: Decimal | None = None


class InvoiceLineItemRead(BaseModel):
    id: UUID
    invoice_id: UUID
    description: str
    quantity: Decimal
    unit_price_egp: Decimal
    total_egp: Decimal
    sort_order: int


class InvoiceLineItemCreate(BaseModel):
    description: str = Field(min_length=1)
    quantity: Decimal = Decimal("1")
    unit_price_egp: Decimal
    sort_order: int = 0


class InvoiceRead(BaseModel):
    id: UUID
    invoice_number: str
    case_id: UUID | None = None
    contact_id: UUID | None = None
    issue_date: date
    due_date: date
    status: InvoiceStatus
    subtotal_egp: Decimal
    tax_rate: Decimal
    tax_egp: Decimal
    discount_egp: Decimal
    total_egp: Decimal
    notes: str | None = None
    created_by: UUID | None = None
    created_at: str
    updated_at: str


class InvoiceDetail(InvoiceRead):
    line_items: list[InvoiceLineItemRead]
    payments: list["PaymentRead"]
    amount_paid: Decimal
    amount_due: Decimal


class InvoiceCreate(BaseModel):
    case_id: UUID | None = None
    contact_id: UUID | None = None
    due_date: date
    tax_rate: Decimal = Decimal("14")
    discount_egp: Decimal = Decimal("0")
    notes: str | None = None
    line_items: list[InvoiceLineItemCreate] = []


class InvoiceUpdate(BaseModel):
    case_id: UUID | None = None
    contact_id: UUID | None = None
    due_date: date | None = None
    tax_rate: Decimal | None = None
    discount_egp: Decimal | None = None
    notes: str | None = None


class PaymentRead(BaseModel):
    id: UUID
    invoice_id: UUID
    amount_egp: Decimal
    payment_date: date
    method: PaymentMethod | None = None
    reference: str | None = None
    notes: str | None = None
    recorded_by: UUID | None = None
    created_at: str


class PaymentCreate(BaseModel):
    amount_egp: Decimal = Field(gt=0)
    payment_date: date
    method: PaymentMethod | None = None
    reference: str | None = None
    notes: str | None = None


class BillingRateRead(BaseModel):
    id: UUID
    user_id: UUID
    rate_egp: Decimal
    effective_from: date
    created_at: str


class BillingRateSet(BaseModel):
    user_id: UUID
    rate_egp: Decimal = Field(ge=0)
    effective_from: date | None = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _te_row(r) -> TimeEntryRead:
    d = dict(r)
    d["created_at"] = d["created_at"].isoformat()
    d["updated_at"] = d["updated_at"].isoformat()
    return TimeEntryRead(**d)


def _inv_row(r) -> InvoiceRead:
    d = dict(r)
    d["created_at"] = d["created_at"].isoformat()
    d["updated_at"] = d["updated_at"].isoformat()
    return InvoiceRead(**d)


def _pay_row(r) -> PaymentRead:
    d = dict(r)
    d["created_at"] = d["created_at"].isoformat()
    return PaymentRead(**d)


async def _get_invoice_or_404(conn, invoice_id: UUID) -> InvoiceRead:
    row = await conn.fetchrow(
        """
        SELECT id, invoice_number, case_id, contact_id, issue_date, due_date,
               status, subtotal_egp, tax_rate, tax_egp, discount_egp, total_egp,
               notes, created_by, created_at, updated_at
        FROM invoices WHERE id = $1
        """,
        invoice_id,
    )
    if row is None:
        raise ApiError(404, "not_found", "الفاتورة غير موجودة")
    return _inv_row(row)


def _compute_totals(
    line_items: list[InvoiceLineItemCreate],
    tax_rate: Decimal,
    discount_egp: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    subtotal = sum(li.quantity * li.unit_price_egp for li in line_items)
    tax = (subtotal * tax_rate / 100).quantize(Decimal("0.01"))
    total = subtotal + tax - discount_egp
    return subtotal, tax, total


# ── Time entries ──────────────────────────────────────────────────────────────

_TE_COLS = (
    "id, case_id, user_id, date, duration_minutes, description, "
    "is_billable, rate_egp, amount_egp, invoice_id, created_at, updated_at"
)


@router.get("/time-entries", response_model=list[TimeEntryRead])
async def list_time_entries(
    user: CurrentUserDep,
    conn: Db,
    case_id: UUID | None = Query(None),
    user_id: UUID | None = Query(None),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
) -> list[TimeEntryRead]:
    conditions: list[str] = []
    params: list = []

    # Non-managers can only see their own entries
    if user.role != MANAGER:
        params.append(user.id)
        conditions.append(f"user_id = ${len(params)}")
    elif user_id:
        params.append(user_id)
        conditions.append(f"user_id = ${len(params)}")

    if case_id:
        params.append(case_id)
        conditions.append(f"case_id = ${len(params)}")
    if from_date:
        params.append(from_date)
        conditions.append(f"date >= ${len(params)}")
    if to_date:
        params.append(to_date)
        conditions.append(f"date <= ${len(params)}")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await conn.fetch(
        f"SELECT {_TE_COLS} FROM time_entries {where} ORDER BY date DESC, created_at DESC LIMIT 500",
        *params,
    )
    return [_te_row(r) for r in rows]


@router.post("/time-entries", response_model=TimeEntryRead, status_code=201)
async def create_time_entry(
    body: TimeEntryCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL, SECRETARY))],
) -> TimeEntryRead:
    # Compute amount if rate is provided
    amount = None
    if body.rate_egp is not None:
        amount = (Decimal(body.duration_minutes) / 60 * body.rate_egp).quantize(Decimal("0.01"))

    row = await conn.fetchrow(
        f"""
        INSERT INTO time_entries
          (case_id, user_id, date, duration_minutes, description, is_billable, rate_egp, amount_egp)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING {_TE_COLS}
        """,
        body.case_id, user.id, body.entry_date, body.duration_minutes,
        body.description, body.is_billable, body.rate_egp, amount,
    )
    return _te_row(row)


@router.patch("/time-entries/{entry_id}", response_model=TimeEntryRead)
async def update_time_entry(
    entry_id: UUID,
    body: TimeEntryUpdate,
    user: CurrentUserDep,
    conn: Db,
) -> TimeEntryRead:
    existing = await conn.fetchrow(
        f"SELECT {_TE_COLS} FROM time_entries WHERE id = $1", entry_id
    )
    if existing is None:
        raise ApiError(404, "not_found", "القيد غير موجود")
    if user.role != MANAGER and existing["user_id"] != user.id:
        raise ApiError(403, "forbidden", "يمكنك تعديل قيودك فقط")
    if existing["invoice_id"] is not None:
        raise ApiError(409, "conflict", "لا يمكن تعديل قيد مرتبط بفاتورة")

    updates = body.model_dump(exclude_unset=True)
    if "entry_date" in updates:
        updates["date"] = updates.pop("entry_date")
    if not updates:
        return _te_row(existing)

    # Re-compute amount if rate or duration changed
    new_rate = updates.get("rate_egp", existing["rate_egp"])
    new_mins = updates.get("duration_minutes", existing["duration_minutes"])
    if new_rate is not None:
        updates["amount_egp"] = (Decimal(new_mins) / 60 * Decimal(new_rate)).quantize(Decimal("0.01"))

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(entry_id)

    row = await conn.fetchrow(
        f"UPDATE time_entries SET {', '.join(parts)}, updated_at=now() WHERE id=${len(params)} RETURNING {_TE_COLS}",
        *params,
    )
    return _te_row(row)


@router.delete("/time-entries/{entry_id}", status_code=200)
async def delete_time_entry(entry_id: UUID, user: CurrentUserDep, conn: Db) -> dict:
    existing = await conn.fetchrow("SELECT id, user_id, invoice_id FROM time_entries WHERE id=$1", entry_id)
    if existing is None:
        raise ApiError(404, "not_found", "القيد غير موجود")
    if user.role != MANAGER and existing["user_id"] != user.id:
        raise ApiError(403, "forbidden", "يمكنك حذف قيودك فقط")
    if existing["invoice_id"] is not None:
        raise ApiError(409, "conflict", "لا يمكن حذف قيد مرتبط بفاتورة")
    await conn.execute("DELETE FROM time_entries WHERE id=$1", entry_id)
    return {"status": "deleted", "id": str(entry_id)}


# ── Invoices ──────────────────────────────────────────────────────────────────

_INV_COLS = (
    "id, invoice_number, case_id, contact_id, issue_date, due_date, status, "
    "subtotal_egp, tax_rate, tax_egp, discount_egp, total_egp, notes, created_by, "
    "created_at, updated_at"
)


@router.get("/invoices", response_model=list[InvoiceRead])
async def list_invoices(
    user: CurrentUserDep,
    conn: Db,
    status: InvoiceStatus | None = Query(None),
    case_id: UUID | None = Query(None),
    contact_id: UUID | None = Query(None),
) -> list[InvoiceRead]:
    conditions: list[str] = []
    params: list = []
    if status:
        params.append(status)
        conditions.append(f"status = ${len(params)}")
    if case_id:
        params.append(case_id)
        conditions.append(f"case_id = ${len(params)}")
    if contact_id:
        params.append(contact_id)
        conditions.append(f"contact_id = ${len(params)}")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await conn.fetch(
        f"SELECT {_INV_COLS} FROM invoices {where} ORDER BY created_at DESC LIMIT 500",
        *params,
    )
    return [_inv_row(r) for r in rows]


@router.post("/invoices", response_model=InvoiceDetail, status_code=201)
async def create_invoice(
    body: InvoiceCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, SECRETARY))],
) -> InvoiceDetail:
    subtotal, tax, total = _compute_totals(body.line_items, body.tax_rate, body.discount_egp)

    inv_row = await conn.fetchrow(
        f"""
        INSERT INTO invoices
          (invoice_number, case_id, contact_id, due_date, tax_rate, discount_egp,
           subtotal_egp, tax_egp, total_egp, notes, created_by)
        VALUES (next_invoice_number(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING {_INV_COLS}
        """,
        body.case_id, body.contact_id, body.due_date, body.tax_rate, body.discount_egp,
        subtotal, tax, total, body.notes, user.id,
    )
    invoice = _inv_row(inv_row)

    line_items: list[InvoiceLineItemRead] = []
    for li in body.line_items:
        li_total = (li.quantity * li.unit_price_egp).quantize(Decimal("0.01"))
        li_row = await conn.fetchrow(
            """
            INSERT INTO invoice_line_items
              (invoice_id, description, quantity, unit_price_egp, total_egp, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, invoice_id, description, quantity, unit_price_egp, total_egp, sort_order
            """,
            invoice.id, li.description, li.quantity, li.unit_price_egp, li_total, li.sort_order,
        )
        line_items.append(InvoiceLineItemRead(**dict(li_row)))

    return InvoiceDetail(**invoice.model_dump(), line_items=line_items, payments=[],
                         amount_paid=Decimal("0"), amount_due=total)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
async def get_invoice(invoice_id: UUID, user: CurrentUserDep, conn: Db) -> InvoiceDetail:
    invoice = await _get_invoice_or_404(conn, invoice_id)

    li_rows = await conn.fetch(
        """
        SELECT id, invoice_id, description, quantity, unit_price_egp, total_egp, sort_order
        FROM invoice_line_items WHERE invoice_id=$1 ORDER BY sort_order, id
        """,
        invoice_id,
    )
    pay_rows = await conn.fetch(
        """
        SELECT id, invoice_id, amount_egp, payment_date, method, reference, notes, recorded_by, created_at
        FROM payments WHERE invoice_id=$1 ORDER BY payment_date
        """,
        invoice_id,
    )
    payments = [_pay_row(r) for r in pay_rows]
    amount_paid = sum(p.amount_egp for p in payments)
    amount_due = invoice.total_egp - amount_paid

    return InvoiceDetail(
        **invoice.model_dump(),
        line_items=[InvoiceLineItemRead(**dict(r)) for r in li_rows],
        payments=payments,
        amount_paid=amount_paid,
        amount_due=amount_due,
    )


@router.patch("/invoices/{invoice_id}", response_model=InvoiceRead)
async def update_invoice(
    invoice_id: UUID,
    body: InvoiceUpdate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, SECRETARY))],
) -> InvoiceRead:
    invoice = await _get_invoice_or_404(conn, invoice_id)
    if invoice.status in ("paid", "cancelled"):
        raise ApiError(409, "conflict", "لا يمكن تعديل فاتورة مدفوعة أو ملغاة")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return invoice

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(invoice_id)

    row = await conn.fetchrow(
        f"UPDATE invoices SET {', '.join(parts)}, updated_at=now() WHERE id=${len(params)} RETURNING {_INV_COLS}",
        *params,
    )
    return _inv_row(row)


@router.post("/invoices/{invoice_id}/send", response_model=InvoiceRead)
async def send_invoice(
    invoice_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, SECRETARY))],
) -> InvoiceRead:
    invoice = await _get_invoice_or_404(conn, invoice_id)
    if invoice.status != "draft":
        raise ApiError(409, "conflict", "يمكن إرسال الفواتير في حالة مسودة فقط")
    row = await conn.fetchrow(
        f"UPDATE invoices SET status='sent', updated_at=now() WHERE id=$1 RETURNING {_INV_COLS}",
        invoice_id,
    )
    # TODO: trigger WhatsApp notification via WAHA if contact has phone
    return _inv_row(row)


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceRead)
async def cancel_invoice(
    invoice_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER))],
) -> InvoiceRead:
    invoice = await _get_invoice_or_404(conn, invoice_id)
    if invoice.status == "paid":
        raise ApiError(409, "conflict", "لا يمكن إلغاء فاتورة مدفوعة")
    row = await conn.fetchrow(
        f"UPDATE invoices SET status='cancelled', updated_at=now() WHERE id=$1 RETURNING {_INV_COLS}",
        invoice_id,
    )
    return _inv_row(row)


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(invoice_id: UUID, user: CurrentUserDep, conn: Db) -> dict:
    """PDF generation stub — returns a placeholder until Pandoc/WeasyPrint is wired."""
    invoice = await _get_invoice_or_404(conn, invoice_id)
    # TODO: generate via WeasyPrint and upload to Supabase Storage
    return {"invoice_id": str(invoice.id), "pdf_url": None,
            "note": "PDF generation not yet implemented — add WeasyPrint to docker-compose."}


# ── Payments ──────────────────────────────────────────────────────────────────

@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentRead])
async def list_payments(invoice_id: UUID, user: CurrentUserDep, conn: Db) -> list[PaymentRead]:
    await _get_invoice_or_404(conn, invoice_id)
    rows = await conn.fetch(
        """
        SELECT id, invoice_id, amount_egp, payment_date, method, reference, notes, recorded_by, created_at
        FROM payments WHERE invoice_id=$1 ORDER BY payment_date
        """,
        invoice_id,
    )
    return [_pay_row(r) for r in rows]


@router.post("/invoices/{invoice_id}/payments", response_model=PaymentRead, status_code=201)
async def record_payment(
    invoice_id: UUID,
    body: PaymentCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, SECRETARY))],
) -> PaymentRead:
    invoice = await _get_invoice_or_404(conn, invoice_id)
    if invoice.status in ("cancelled",):
        raise ApiError(409, "conflict", "لا يمكن تسجيل دفعة لفاتورة ملغاة")

    pay_row = await conn.fetchrow(
        """
        INSERT INTO payments (invoice_id, amount_egp, payment_date, method, reference, notes, recorded_by)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        RETURNING id, invoice_id, amount_egp, payment_date, method, reference, notes, recorded_by, created_at
        """,
        invoice_id, body.amount_egp, body.payment_date, body.method,
        body.reference, body.notes, user.id,
    )

    # Update invoice status based on total paid
    paid_total = await conn.fetchval(
        "SELECT coalesce(sum(amount_egp),0) FROM payments WHERE invoice_id=$1", invoice_id
    )
    new_status: str
    if paid_total >= invoice.total_egp:
        new_status = "paid"
    elif paid_total > 0:
        new_status = "partial"
    else:
        new_status = invoice.status

    if new_status != invoice.status:
        await conn.execute(
            "UPDATE invoices SET status=$1, updated_at=now() WHERE id=$2",
            new_status, invoice_id,
        )

    return _pay_row(pay_row)


# ── Billing rates ─────────────────────────────────────────────────────────────

@router.get("/billing-rates", response_model=list[BillingRateRead])
async def list_billing_rates(
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER))],
    conn: Db,
) -> list[BillingRateRead]:
    rows = await conn.fetch(
        "SELECT id, user_id, rate_egp, effective_from, created_at FROM billing_rates ORDER BY user_id, effective_from DESC"
    )
    result = []
    for r in rows:
        d = dict(r)
        d["created_at"] = d["created_at"].isoformat()
        result.append(BillingRateRead(**d))
    return result


@router.post("/billing-rates", response_model=BillingRateRead, status_code=201)
async def set_billing_rate(
    body: BillingRateSet,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER))],
) -> BillingRateRead:
    effective = body.effective_from or date.today()
    row = await conn.fetchrow(
        """
        INSERT INTO billing_rates (user_id, rate_egp, effective_from)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, effective_from)
        DO UPDATE SET rate_egp = EXCLUDED.rate_egp
        RETURNING id, user_id, rate_egp, effective_from, created_at
        """,
        body.user_id, body.rate_egp, effective,
    )
    d = dict(row)
    d["created_at"] = d["created_at"].isoformat()
    return BillingRateRead(**d)
