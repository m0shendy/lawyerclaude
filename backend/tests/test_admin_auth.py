"""Tests for the platform admin console authentication (feature 003, US1).

Tests (per tasks.md T014 + quickstart §1):
  - Lockout after 5 failures; success resets window
  - Firm-role token → 403 on /admin/me
  - aal1 token (no MFA) → 401 on /admin/me
  - Stale session (last_seen > 30 min) → 401
  - revoke-all kills a live session
  - /admin/me returns 401 with no token

These are integration-style unit tests that mock the DB pool and GoTrue calls
so they run without a live Supabase connection.
"""

from __future__ import annotations

import json
import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import httpx

from app.main import app


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_aal2_claims(sub: str | None = None, session_id: str | None = None, aal: str = "aal2") -> dict:
    return {
        "sub": sub or str(uuid4()),
        "aal": aal,
        "session_id": session_id or str(uuid4()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }


def _make_firm_role_claims(sub: str | None = None, role: str = "lawyer") -> dict:
    # aal2 so it passes the MFA check; platform_operators lookup returns None → 403.
    return {
        "sub": sub or str(uuid4()),
        "aal": "aal2",
        "session_id": str(uuid4()),
        "role": role,
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }


# ── /admin/me — no token → 401 ────────────────────────────────────────────────

@pytest.mark.anyio
async def test_admin_me_no_token_returns_401() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/me")
    assert resp.status_code == 401


# ── /admin/me — firm-role token → 403 ────────────────────────────────────────

@pytest.mark.anyio
async def test_admin_me_firm_role_token_returns_403() -> None:
    """A valid firm-role JWT must be rejected with 403 on every /admin/* route."""
    claims = _make_firm_role_claims()

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)  # not in platform_operators
    mock_conn.execute = AsyncMock()

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    with (
        patch("app.core.operator._decode_token", return_value=claims),
        patch("app.core.operator.get_service_pool", AsyncMock(return_value=mock_pool)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-firm-token"},
        ) as client:
            resp = await client.get("/admin/me")

    assert resp.status_code == 403


# ── /admin/me — aal1 token (no MFA) → 401 ────────────────────────────────────

@pytest.mark.anyio
async def test_admin_me_aal1_token_returns_401() -> None:
    """An aal1 operator token (MFA not completed) must be rejected."""
    claims = _make_aal2_claims(aal="aal1")

    with patch("app.core.operator._decode_token", return_value=claims):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-aal1-token"},
        ) as client:
            resp = await client.get("/admin/me")

    assert resp.status_code == 401


# ── /admin/me — stale session → 401 ──────────────────────────────────────────

@pytest.mark.anyio
async def test_admin_me_stale_session_returns_401() -> None:
    """An operator session with last_seen > 30 min must be rejected and purged."""
    sub = str(uuid4())
    session_id = str(uuid4())
    claims = _make_aal2_claims(sub=sub, session_id=session_id)
    stale_time = datetime.now(tz=timezone.utc) - timedelta(minutes=31)

    op_row = {"auth_user_id": sub, "display_name": "Test Op", "is_active": True}
    sess_row = {"last_seen": stale_time}

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return op_row
        if "operator_sessions" in query:
            return sess_row
        return None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.execute = AsyncMock()

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    with (
        patch("app.core.operator._decode_token", return_value=claims),
        patch("app.core.operator.get_service_pool", AsyncMock(return_value=mock_pool)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-stale-token"},
        ) as client:
            resp = await client.get("/admin/me")

    assert resp.status_code == 401
    # Verify the stale session was purged
    delete_calls = [
        call for call in mock_conn.execute.call_args_list
        if "DELETE FROM operator_sessions" in str(call)
    ]
    assert len(delete_calls) >= 1


# ── lockout: 5 failures locks the account ────────────────────────────────────

@pytest.mark.anyio
async def test_login_lockout_after_5_failures() -> None:
    """5 consecutive failures within 15 min must return 423."""
    # Simulate 5 recent failure rows with no intervening success
    failure_rows = [{"succeeded": False}] * 5

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=failure_rows)
    mock_conn.execute = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    with patch("app.api.admin.get_service_pool", AsyncMock(return_value=mock_pool)):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/login",
                json={"email": "op@test.com", "password": "bad"},
            )

    assert resp.status_code == 423


# ── lockout resets when a success is recorded ─────────────────────────────────

@pytest.mark.anyio
async def test_login_lockout_resets_after_success() -> None:
    """An intervening success row must reset the lockout window (fewer than threshold failures after it)."""
    # Rows ordered desc: 3 failures then 1 success — window resets at success
    rows = [{"succeeded": False}, {"succeeded": False}, {"succeeded": False}, {"succeeded": True}]

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=rows)
    mock_conn.execute = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    # After passing lockout it will try GoTrue — mock a failure so we get 401 not 500
    with (
        patch("app.api.admin.get_service_pool", AsyncMock(return_value=mock_pool)),
        patch(
            "app.api.admin.httpx.AsyncClient",
            return_value=AsyncMock(
                __aenter__=AsyncMock(
                    return_value=AsyncMock(
                        post=AsyncMock(return_value=AsyncMock(status_code=401, json=AsyncMock(return_value={})))
                    )
                ),
                __aexit__=AsyncMock(return_value=False),
            ),
        ),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/login",
                json={"email": "op@test.com", "password": "wrong"},
            )

    # Should reach GoTrue and fail with 401 (not locked out at 423)
    assert resp.status_code == 401


# ── revoke-all kills the live session ─────────────────────────────────────────

@pytest.mark.anyio
async def test_revoke_all_kills_live_session() -> None:
    """POST /admin/sessions/revoke-all must delete all sessions for the operator."""
    sub = str(uuid4())
    session_id = str(uuid4())
    claims = _make_aal2_claims(sub=sub, session_id=session_id)
    now = datetime.now(tz=timezone.utc)

    op_row = {"auth_user_id": sub, "display_name": "Test Op", "is_active": True}
    sess_row = {"last_seen": now}

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return op_row
        if "operator_sessions" in query:
            return sess_row
        return None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.execute = AsyncMock(return_value="DELETE 2")

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    with (
        patch("app.core.operator._decode_token", return_value=claims),
        patch("app.core.operator.get_service_pool", AsyncMock(return_value=mock_pool)),
        patch("app.api.admin.get_service_pool", AsyncMock(return_value=mock_pool)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-aal2-token"},
        ) as client:
            resp = await client.post("/admin/sessions/revoke-all")

    assert resp.status_code == 204
    # Confirm DELETE was called for operator_sessions with this operator_id
    delete_calls = [
        call for call in mock_conn.execute.call_args_list
        if "DELETE FROM operator_sessions" in str(call) and "operator_id" in str(call)
    ]
    assert len(delete_calls) >= 1
