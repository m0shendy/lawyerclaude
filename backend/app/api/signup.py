"""Public signup + billing endpoints (WP-S3). [C-I v2]

``POST /signup`` is the ONLY unauthenticated write path in the product:
    firm → GoTrue credential → manager profile → firm_settings → trial sub.
Everything runs on the SERVICE connection (there is no user yet) and every
mutation is audited with context ``public:signup``. [C-III]

``POST /billing/initiate``    (manager) → Paymob iframe URL for a plan.
``POST /billing/paymob-webhook`` (public) → HMAC-verified, idempotent via
``billing_events``; only a verified, amount-reconciled, successful transaction
activates the firm. The webhook NEVER trusts client-supplied state.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field

from app.billing import PLANS
from app.billing.paymob import PaymobError, create_payment_url, reconcile_amount, verify_webhook_hmac
from app.core.config import get_settings
from app.core.db import Db, db_connection
from app.core.errors import ApiError
from app.core.rbac import MANAGER, require_roles
from app.core.security import CurrentUser

ManagerDep = Depends(require_roles(MANAGER))

logger = logging.getLogger(__name__)
router = APIRouter(tags=["signup-billing"])

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


class SignupIn(BaseModel):
    firm_name: str = Field(min_length=2, max_length=120)
    manager_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    phone: str | None = Field(default=None, max_length=20)


class SignupOut(BaseModel):
    firm_id: UUID
    slug: str
    trial_ends_at: str


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower().strip()).strip("-") or "firm"
    return base[:40]


@router.post("/signup", response_model=SignupOut, status_code=201)
async def signup(body: SignupIn) -> SignupOut:
    settings = get_settings()

    async with db_connection(None, context="public:signup") as conn:
        # 1) firm row — unique slug with numeric suffix on collision.
        slug = _slugify(body.firm_name)
        for attempt in range(1, 50):
            try_slug = slug if attempt == 1 else f"{slug}-{attempt}"
            firm_id = await conn.fetchval(
                "INSERT INTO firms (name, slug) VALUES ($1, $2) "
                "ON CONFLICT (slug) DO NOTHING RETURNING id",
                body.firm_name, try_slug,
            )
            if firm_id:
                slug = try_slug
                break
        else:
            raise ApiError(409, "invalid_state", "تعذر إنشاء معرف فريد للمكتب — جرّب اسمًا آخر")

        # 2) GoTrue credential (auth provider owns identity).
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{settings.supabase_url}/auth/v1/admin/users",
                    headers={
                        "Authorization": f"Bearer {settings.supabase_service_key}",
                        "apikey": settings.supabase_service_key,
                    },
                    json={"email": body.email, "password": body.password, "email_confirm": True},
                )
        except httpx.HTTPError as exc:
            await conn.execute("DELETE FROM firms WHERE id = $1", firm_id)
            raise ApiError(502, "auth_provider_error", "تعذر الاتصال بخدمة المصادقة") from exc
        if resp.status_code not in (200, 201):
            await conn.execute("DELETE FROM firms WHERE id = $1", firm_id)
            if resp.status_code in (409, 422):
                raise ApiError(409, "invalid_state", "البريد الإلكتروني مسجل بالفعل")
            logger.warning("signup: GoTrue create failed (status=%s)", resp.status_code)
            raise ApiError(502, "auth_provider_error", "تعذر إنشاء حساب المصادقة")
        auth_user_id = resp.json().get("id")

        # 3) manager profile + per-firm settings + trial subscription.
        await conn.execute(
            "INSERT INTO users (firm_id, auth_user_id, full_name, email, phone, role) "
            "VALUES ($1, $2, $3, $4, $5, 'partner_manager')",
            firm_id, UUID(auth_user_id), body.manager_name, body.email, body.phone,
        )
        await conn.execute(
            "INSERT INTO firm_settings (firm_id, firm_name) VALUES ($1, $2)",
            firm_id, body.firm_name,
        )
        await conn.execute(
            "INSERT INTO subscriptions (firm_id, plan, provider, status) "
            "VALUES ($1, 'basic', 'manual', 'trialing')",
            firm_id,
        )
        trial_ends = await conn.fetchval("SELECT trial_ends_at FROM firms WHERE id = $1", firm_id)

    return SignupOut(firm_id=firm_id, slug=slug, trial_ends_at=str(trial_ends))


class InitiateIn(BaseModel):
    plan: str


@router.post("/billing/initiate")
async def initiate_payment(
    body: InitiateIn,
    conn: Db,
    manager: CurrentUser = ManagerDep,
) -> dict[str, str]:
    if body.plan not in PLANS:
        raise ApiError(400, "bad_request", "خطة غير معروفة")
    firm = await conn.fetchrow("SELECT name FROM firms WHERE id = $1", manager.firm_id)
    try:
        result = await create_payment_url(
            plan_code=body.plan,
            firm_name=firm["name"] if firm else "",
            email=manager.email,
            phone=manager.phone or "",
        )
    except PaymobError:
        logger.exception("billing: Paymob initiation failed")
        raise ApiError(502, "payment_provider_error", "تعذر بدء عملية الدفع — حاول لاحقًا")

    # Stash the pending order → firm/plan mapping for the webhook to resolve.
    async with db_connection(None, context="billing:initiate") as sconn:
        await sconn.execute(
            "INSERT INTO billing_events (provider, provider_ref, payload) "
            "VALUES ('paymob', $1, $2::jsonb) ON CONFLICT DO NOTHING",
            f"order-{result['order_id']}",
            json.dumps({"kind": "order_created", "firm_id": str(manager.firm_id), "plan": body.plan}),
        )
    return {"iframe_url": result["iframe_url"]}


@router.post("/billing/paymob-webhook")
async def paymob_webhook(request: Request) -> dict[str, str]:
    raw = await request.json()
    obj = raw.get("obj") or {}
    received_hmac = request.query_params.get("hmac", "")

    # 1) HMAC first. Unverifiable → reject (logged, never processed).
    if not verify_webhook_hmac(obj, received_hmac):
        logger.warning("billing: webhook HMAC verification FAILED — rejected")
        raise ApiError(401, "invalid_signature", "rejected")

    txn_id = str(obj.get("id", ""))
    order_id = str((obj.get("order") or {}).get("id", ""))
    success = bool(obj.get("success"))

    async with db_connection(None, context="billing:webhook") as conn:
        # 2) Idempotent inbox: same transaction processed once.
        inserted = await conn.fetchval(
            "INSERT INTO billing_events (provider, provider_ref, payload) "
            "VALUES ('paymob', $1, $2::jsonb) ON CONFLICT DO NOTHING RETURNING id",
            f"txn-{txn_id}", json.dumps({"kind": "transaction", "obj": obj}),
        )
        if inserted is None:
            return {"status": "duplicate_ignored"}

        # 3) Resolve firm/plan from the initiation event (server-side mapping).
        pending = await conn.fetchrow(
            "SELECT payload FROM billing_events WHERE provider='paymob' AND provider_ref=$1",
            f"order-{order_id}",
        )
        if pending is None:
            logger.warning("billing: webhook for unknown order %s — stored, not applied", order_id)
            return {"status": "unknown_order"}
        meta = pending["payload"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        firm_id, plan = UUID(meta["firm_id"]), meta["plan"]

        # 4) Amount reconciliation against the plan table — never trust payload.
        if not success or not reconcile_amount(plan, obj.get("amount_cents")):
            await conn.execute(
                "UPDATE billing_events SET processed_at = now() WHERE provider_ref = $1",
                f"txn-{txn_id}",
            )
            return {"status": "not_applied"}

        # 5) Activate: subscription + firm status (shared path with manual payments).
        from app.billing.activation import activate_subscription  # noqa: PLC0415
        await activate_subscription(
            conn, firm_id, plan, provider="paymob", provider_sub_id=str(txn_id)
        )
        await conn.execute(
            "UPDATE billing_events SET processed_at = now() WHERE provider_ref = $1",
            f"txn-{txn_id}",
        )
    logger.info("billing: firm %s activated on plan %s", firm_id, plan)
    return {"status": "applied"}
