"""Tests for firm lifecycle admin endpoints (feature 003, US3).

Tests (per tasks.md T022 + quickstart §3):
  - suspend → firm API blocked (T020 suspension propagation)
  - extend-trial on cancelled firm → 422
  - change-plan updates subscription with audit row
  - missing confirm → 422 and no state change
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import httpx

from app.main import app


def _make_aal2_claims(sub: str, session_id: str) -> dict:
    return {
        "sub": sub,
        "aal": "aal2",
        "session_id": session_id,
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }


def _make_operator_mocks(sub: str, session_id: str):
    """Return (claims, mock_pool) for a valid operator session."""
    claims = _make_aal2_claims(sub, session_id)
    now = datetime.now(tz=timezone.utc)
    op_row = {"auth_user_id": sub, "display_name": "Test Op", "is_active": True}
    sess_row = {"last_seen": now}
    created_sess = {"created_at": now}

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return op_row
        if "operator_sessions" in query and "last_seen" in query:
            return sess_row
        if "operator_sessions" in query and "created_at" in query:
            return created_sess
        return None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.execute = AsyncMock(return_value="UPDATE 1")
    mock_conn.fetchval = AsyncMock(return_value=datetime.now(tz=timezone.utc) + timedelta(days=7))

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    return claims, mock_conn, mock_pool


# ── suspend blocks a firm user ────────────────────────────────────────────────

@pytest.mark.anyio
async def test_suspended_firm_user_gets_403() -> None:
    """After firm is suspended, any firm user's request must return 403."""
    # This tests the T020 fix in security.py — load_user_by_auth_id now checks
    # firms.status and raises 403 for suspended/cancelled firms.
    user_auth_id = str(uuid4())

    async def mock_fetchrow(query, *args):
        if "users u" in query and "JOIN firms" in query:
            return {
                "id": uuid4(),
                "auth_user_id": uuid4(),
                "firm_id": uuid4(),
                "full_name": "Test Lawyer",
                "email": "test@firm.com",
                "phone": None,
                "role": "lawyer",
                "status": "active",
                "firm_status": "suspended",
            }
        return None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=mock_fetchrow)
    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    from app.core.security import _decode_token
    firm_claims = {
        "sub": user_auth_id,
        "aal": "aal1",
        "session_id": str(uuid4()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }

    with (
        patch("app.core.security._decode_token", return_value=firm_claims),
        patch("app.core.db.get_service_pool", AsyncMock(return_value=mock_pool)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-firm-token"},
        ) as client:
            resp = await client.get("/me")

    assert resp.status_code == 403


# ── extend-trial on cancelled firm → 422 ──────────────────────────────────────

@pytest.mark.anyio
async def test_extend_trial_on_cancelled_firm_returns_422() -> None:
    sub = str(uuid4())
    session_id = str(uuid4())
    claims, mock_conn, mock_pool = _make_operator_mocks(sub, session_id)

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return {"auth_user_id": sub, "display_name": "Op", "is_active": True}
        if "operator_sessions" in query and "last_seen" in query:
            return {"last_seen": datetime.now(tz=timezone.utc)}
        if "status, trial_ends_at" in query:
            return {"status": "cancelled", "trial_ends_at": None}
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
                f"/admin/firms/{uuid4()}/extend-trial",
                json={"days": 7, "confirm": True},
            )

    assert resp.status_code == 422


# ── missing confirm → model-level validation (422 semantics) ──────────────────

def test_confirm_request_rejects_false() -> None:
    """ConfirmRequest.confirm=False must raise a validation error."""
    from pydantic import ValidationError as PydanticValidationError
    from app.models.admin import ConfirmRequest
    with pytest.raises(PydanticValidationError):
        ConfirmRequest(confirm=False)


def test_confirm_request_missing_field_raises() -> None:
    """ConfirmRequest without the confirm field must raise a validation error."""
    from pydantic import ValidationError as PydanticValidationError
    from app.models.admin import ConfirmRequest
    with pytest.raises(PydanticValidationError):
        ConfirmRequest()  # type: ignore[call-arg]


# ── change-plan writes subscription update (audit via trigger) ────────────────

@pytest.mark.anyio
async def test_change_plan_updates_subscription() -> None:
    sub = str(uuid4())
    session_id = str(uuid4())
    firm_id = uuid4()
    claims, mock_conn, mock_pool = _make_operator_mocks(sub, session_id)

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return {"auth_user_id": sub, "display_name": "Op", "is_active": True}
        if "operator_sessions" in query and "last_seen" in query:
            return {"last_seen": datetime.now(tz=timezone.utc)}
        if "SELECT id FROM firms" in query:
            return {"id": firm_id}
        return None

    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.execute = AsyncMock(return_value="UPDATE 1")

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
                f"/admin/firms/{firm_id}/change-plan",
                json={"plan": "pro", "confirm": True},
            )

    assert resp.status_code == 200
    assert resp.json()["plan"] == "pro"

    # Verify the UPDATE subscriptions was called
    update_calls = [
        c for c in mock_conn.execute.call_args_list
        if "UPDATE subscriptions" in str(c)
    ]
    assert len(update_calls) >= 1
