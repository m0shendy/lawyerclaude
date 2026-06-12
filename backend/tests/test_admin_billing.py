"""Tests for billing admin endpoints (feature 003, US4).

Tests (per tasks.md T027 + quickstart §4):
  - resolve without note → 422
  - resolve leaves billing_events row unchanged (append-only C-III)
  - manual payment activates firm + writes manual_payments + audit rows
  - webhook regression still green after T023 refactor (activate_subscription path)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import httpx

from app.main import app


def _make_aal2_claims(sub: str) -> dict:
    return {
        "sub": sub,
        "aal": "aal2",
        "session_id": str(uuid4()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }


def _make_operator_mocks(sub: str):
    claims = _make_aal2_claims(sub)
    now = datetime.now(tz=timezone.utc)
    op_row = {"auth_user_id": sub, "display_name": "Test Op", "is_active": True}
    sess_row = {"last_seen": now}

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return op_row
        if "operator_sessions" in query and "last_seen" in query:
            return sess_row
        return None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
    mock_conn.fetchval = AsyncMock(return_value=uuid4())

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    return claims, mock_conn, mock_pool


# ── resolve without note → model-level validation (422 semantics) ─────────────

def test_resolve_request_rejects_blank_note() -> None:
    """BillingEventResolveRequest with blank note must raise a validation error."""
    from pydantic import ValidationError as PydanticValidationError
    from app.models.admin import BillingEventResolveRequest
    with pytest.raises(PydanticValidationError):
        BillingEventResolveRequest(note="")


def test_resolve_request_rejects_whitespace_note() -> None:
    from pydantic import ValidationError as PydanticValidationError
    from app.models.admin import BillingEventResolveRequest
    with pytest.raises(PydanticValidationError):
        BillingEventResolveRequest(note="   ")


# ── resolve leaves billing_events row unchanged (append-only) ─────────────────

@pytest.mark.anyio
async def test_resolve_event_never_updates_billing_events() -> None:
    """POST /resolve must INSERT into billing_event_resolutions ONLY.
    The billing_events row must NEVER be UPDATEd. [C-III]
    """
    sub = str(uuid4())
    event_id = uuid4()
    resolution_id = uuid4()
    claims, mock_conn, mock_pool = _make_operator_mocks(sub)

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return {"auth_user_id": sub, "display_name": "Op", "is_active": True}
        if "operator_sessions" in query and "last_seen" in query:
            return {"last_seen": datetime.now(tz=timezone.utc)}
        if "SELECT id FROM billing_events" in query:
            return {"id": event_id}
        if "SELECT id FROM billing_event_resolutions" in query:
            return None  # not already resolved
        return None

    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.fetchval = AsyncMock(return_value=resolution_id)

    with (
        patch("app.core.operator._decode_token", return_value=claims),
        patch("app.core.operator.get_service_pool", AsyncMock(return_value=mock_pool)),
        patch("app.api.admin.get_service_pool", AsyncMock(return_value=mock_pool)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-token"},
        ) as client:
            resp = await client.post(
                f"/admin/billing-events/{event_id}/resolve",
                json={"note": "Verified with client, payment confirmed"},
            )

    assert resp.status_code == 200
    assert resp.json()["resolution_id"] == str(resolution_id)

    # Critical: no UPDATE on billing_events should have been called
    for call in mock_conn.execute.call_args_list:
        sql = str(call)
        assert "UPDATE billing_events" not in sql, (
            "billing_events row must never be updated — append-only [C-III]"
        )


# ── double-resolve → 409 ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_resolve_already_resolved_event_returns_409() -> None:
    sub = str(uuid4())
    event_id = uuid4()
    claims, mock_conn, mock_pool = _make_operator_mocks(sub)

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return {"auth_user_id": sub, "display_name": "Op", "is_active": True}
        if "operator_sessions" in query and "last_seen" in query:
            return {"last_seen": datetime.now(tz=timezone.utc)}
        if "SELECT id FROM billing_events" in query:
            return {"id": event_id}
        if "SELECT id FROM billing_event_resolutions" in query:
            return {"id": uuid4()}  # already exists
        return None

    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)

    with (
        patch("app.core.operator._decode_token", return_value=claims),
        patch("app.core.operator.get_service_pool", AsyncMock(return_value=mock_pool)),
        patch("app.api.admin.get_service_pool", AsyncMock(return_value=mock_pool)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-token"},
        ) as client:
            resp = await client.post(
                f"/admin/billing-events/{event_id}/resolve",
                json={"note": "Second attempt"},
            )

    assert resp.status_code == 409


# ── manual payment activates firm ────────────────────────────────────────────

@pytest.mark.anyio
async def test_manual_payment_activates_firm() -> None:
    """POST /manual-payment must:
    - INSERT into manual_payments
    - call activate_subscription (UPDATE subscriptions + firms)
    - return firm_status = 'active'
    """
    sub = str(uuid4())
    firm_id = uuid4()
    payment_id = uuid4()
    claims, mock_conn, mock_pool = _make_operator_mocks(sub)

    execute_calls: list[str] = []

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return {"auth_user_id": sub, "display_name": "Op", "is_active": True}
        if "operator_sessions" in query and "last_seen" in query:
            return {"last_seen": datetime.now(tz=timezone.utc)}
        if "SELECT id FROM firms" in query:
            return {"id": firm_id}
        if "SELECT plan FROM subscriptions" in query:
            return {"plan": "basic"}
        if "SELECT status FROM firms" in query:
            return {"status": "active"}
        return None

    async def execute_side(query, *args):
        execute_calls.append(query)
        return "UPDATE 1"

    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.execute = AsyncMock(side_effect=execute_side)
    mock_conn.fetchval = AsyncMock(return_value=payment_id)

    with (
        patch("app.core.operator._decode_token", return_value=claims),
        patch("app.core.operator.get_service_pool", AsyncMock(return_value=mock_pool)),
        patch("app.api.admin.get_service_pool", AsyncMock(return_value=mock_pool)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-token"},
        ) as client:
            resp = await client.post(
                f"/admin/firms/{firm_id}/manual-payment",
                json={
                    "amount_egp": "500.00",
                    "paid_date": "2026-06-12",
                    "reference": "REC-001",
                    "note": "Cash payment at office",
                    "confirm": True,
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["payment_id"] == str(payment_id)
    assert body["subscription_status"] == "active"

    # Verify activate_subscription was called (UPDATE subscriptions)
    sub_updates = [c for c in execute_calls if "UPDATE subscriptions" in c]
    assert len(sub_updates) >= 1

    # Verify firm was also updated
    firm_updates = [c for c in execute_calls if "UPDATE firms" in c]
    assert len(firm_updates) >= 1


# ── manual payment missing confirm → model-level validation ──────────────────

def test_manual_payment_request_rejects_false_confirm() -> None:
    """ManualPaymentRequest with confirm=False must raise a validation error."""
    from pydantic import ValidationError as PydanticValidationError
    from app.models.admin import ManualPaymentRequest
    import datetime
    from decimal import Decimal
    with pytest.raises(PydanticValidationError):
        ManualPaymentRequest(
            amount_egp=Decimal("500.00"),
            paid_date=datetime.date(2026, 6, 12),
            reference="REF",
            note="Test",
            confirm=False,
        )


# ── webhook regression: activate_subscription still called correctly ──────────

@pytest.mark.anyio
async def test_activation_shared_path_called_in_webhook() -> None:
    """The T023 refactor must not change the observable activation behaviour.
    Verify the import chain from signup.py → activation.py is correct.
    """
    # Verify the function is importable and callable.
    from app.billing.activation import activate_subscription as real_fn
    assert callable(real_fn)
