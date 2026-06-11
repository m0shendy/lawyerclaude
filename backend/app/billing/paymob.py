"""Paymob integration (Egypt) — WP-S3.

Flow (Paymob "Accept" API):
    1. ``POST /auth/tokens``          (api_key)            → auth token
    2. ``POST /ecommerce/orders``     (amount, merchant)   → order id
    3. ``POST /acceptance/payment_keys``                   → payment key
    4. Client opens the iframe URL with that key and pays.
    5. Paymob calls our webhook (transaction processed callback). We verify the
       HMAC over the documented concatenated-field string, store the event
       idempotently in ``billing_events``, and only then mutate
       ``subscriptions`` / ``firms``.

SECURITY INVARIANTS:
* The webhook HMAC check is mandatory — an unverifiable callback is rejected
  and logged, never processed. Without this anyone could activate a firm.
* Amounts are reconciled against ``PLANS`` server-side; the webhook's amount is
  checked, not trusted.
* Secrets (api key, HMAC secret) come from env settings; never logged. [C-III]
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.billing import PLANS
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_BASE = "https://accept.paymob.com/api"

# Paymob's documented HMAC field order for transaction callbacks.
_HMAC_FIELDS = (
    "amount_cents",
    "created_at",
    "currency",
    "error_occured",
    "has_parent_transaction",
    "id",
    "integration_id",
    "is_3d_secure",
    "is_auth",
    "is_capture",
    "is_refunded",
    "is_standalone_payment",
    "is_voided",
    "order.id",
    "owner",
    "pending",
    "source_data.pan",
    "source_data.sub_type",
    "source_data.type",
    "success",
)


class PaymobError(RuntimeError):
    """Raised when a Paymob API step fails."""


def _dig(obj: dict[str, Any], dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(part, "")
    return cur


def verify_webhook_hmac(payload_obj: dict[str, Any], received_hmac: str) -> bool:
    """Verify Paymob's transaction-callback HMAC. Constant-time compare."""
    secret = get_settings().paymob_hmac_secret
    if not secret or not received_hmac:
        return False
    concat = "".join(_to_hmac_str(_dig(payload_obj, f)) for f in _HMAC_FIELDS)
    digest = hmac.new(secret.encode(), concat.encode(), hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, received_hmac.lower())


def _to_hmac_str(value: Any) -> str:
    # Paymob stringifies booleans lowercase in the HMAC source string.
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


async def create_payment_url(*, plan_code: str, firm_name: str, email: str, phone: str) -> dict[str, str]:
    """Run steps 1–3 and return the hosted-iframe URL for the client.

    Returns {"iframe_url": ..., "order_id": ...}. Raises PaymobError on any
    step failure (surfaced to the user as a generic Arabic payment error).
    """
    settings = get_settings()
    if not settings.paymob_api_key or not settings.paymob_integration_id:
        raise PaymobError("Paymob is not configured")
    plan = PLANS.get(plan_code)
    if plan is None:
        raise PaymobError(f"unknown plan {plan_code!r}")
    amount_cents = plan.monthly_egp * 100

    async with httpx.AsyncClient(timeout=20) as client:
        # 1) auth token
        r = await client.post(f"{_BASE}/auth/tokens", json={"api_key": settings.paymob_api_key})
        if r.status_code != 201:
            raise PaymobError(f"auth step failed ({r.status_code})")
        token = r.json()["token"]

        # 2) order
        r = await client.post(
            f"{_BASE}/ecommerce/orders",
            json={
                "auth_token": token,
                "delivery_needed": "false",
                "amount_cents": str(amount_cents),
                "currency": "EGP",
                "items": [{"name": f"lawyerclaude {plan.code} (شهري)", "amount_cents": str(amount_cents), "quantity": "1"}],
            },
        )
        if r.status_code != 201:
            raise PaymobError(f"order step failed ({r.status_code})")
        order_id = r.json()["id"]

        # 3) payment key
        r = await client.post(
            f"{_BASE}/acceptance/payment_keys",
            json={
                "auth_token": token,
                "amount_cents": str(amount_cents),
                "expiration": 3600,
                "order_id": order_id,
                "billing_data": {
                    "email": email,
                    "phone_number": phone or "NA",
                    "first_name": firm_name[:50] or "NA",
                    "last_name": "NA",
                    "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA",
                    "shipping_method": "NA", "postal_code": "NA",
                    "city": "NA", "country": "EG", "state": "NA",
                },
                "currency": "EGP",
                "integration_id": int(settings.paymob_integration_id),
            },
        )
        if r.status_code != 201:
            raise PaymobError(f"payment key step failed ({r.status_code})")
        payment_key = r.json()["token"]

    iframe_url = (
        f"https://accept.paymob.com/api/acceptance/iframes/"
        f"{settings.paymob_iframe_id}?payment_token={payment_key}"
    )
    return {"iframe_url": iframe_url, "order_id": str(order_id)}


def reconcile_amount(plan_code: str, amount_cents: Any) -> bool:
    """Server-side amount check — the webhook's amount must match the plan."""
    plan = PLANS.get(plan_code)
    try:
        return plan is not None and int(amount_cents) == plan.monthly_egp * 100
    except (TypeError, ValueError):
        return False
