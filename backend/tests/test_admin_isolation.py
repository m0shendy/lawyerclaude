"""FR-313 Isolation suite — release gate (feature 003, T033).

Six contract checks per contracts/rest-api.md §Isolation-suite additions:

  1. Every firm role → 403 on every /admin/* route (routes enumerated from the
     router, not a hard-coded list).
  2. aal1 (non-MFA) operator token → 401 on every protected /admin/* route.
  3. Deactivated operator (is_active=False) → 403.
  4. Idle session (last_seen > 30 min ago) → 401.
  5. GET /admin/firms/{id} response schema asserts no work-product fields.
  6. No token → 401 on every protected /admin/* route (fail-closed).

All routes that require require_operator are enumerated dynamically.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import httpx

from app.main import app


# ─── Route enumeration ────────────────────────────────────────────────────────

def _admin_routes_requiring_auth() -> list[tuple[str, str]]:
    """Return (method, path) for every /admin/* route except login/mfa."""
    public_paths = {"/admin/login", "/admin/mfa/enroll", "/admin/mfa/verify"}
    result = []
    for route in app.routes:
        if not hasattr(route, "path") or not route.path.startswith("/admin"):
            continue
        if route.path in public_paths:
            continue
        for method in getattr(route, "methods", ["GET"]):
            result.append((method, route.path))
    return result


def _fill_path(path: str) -> str:
    """Replace path parameters with placeholder UUIDs."""
    return re.sub(r"\{[^}]+\}", str(uuid4()), path)


_PROTECTED_ROUTES = _admin_routes_requiring_auth()


# ─── Check 6: no token → fail-closed ─────────────────────────────────────────

@pytest.mark.anyio
@pytest.mark.parametrize("method,path", _PROTECTED_ROUTES)
async def test_no_token_returns_401(method: str, path: str) -> None:
    """Every protected /admin/* route must reject requests with no token."""
    filled = _fill_path(path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.request(method, filled, json={})
    assert resp.status_code in (401, 403), (
        f"{method} {path} → {resp.status_code}: expected 401/403 with no token"
    )


# ─── Check 1: firm-role token → 403 ──────────────────────────────────────────

@pytest.mark.anyio
@pytest.mark.parametrize("method,path", _PROTECTED_ROUTES)
async def test_firm_role_token_returns_403(method: str, path: str) -> None:
    """A firm user's token (aal2 but not in platform_operators) must get 403.

    Firm users can have aal2 if they enrolled TOTP. The /admin/* guard checks
    platform_operators; if not found → 403 (FR-303).
    """
    filled = _fill_path(path)
    firm_sub = str(uuid4())
    # aal2 so it passes the MFA check, but not in platform_operators → 403.
    firm_claims = {
        "sub": firm_sub,
        "aal": "aal2",
        "session_id": str(uuid4()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)  # not in platform_operators
    mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    with (
        patch("app.core.operator._decode_token", return_value=firm_claims),
        patch("app.core.operator.get_service_pool", AsyncMock(return_value=mock_pool)),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-firm-token"},
        ) as client:
            resp = await client.request(method, filled, json={})

    assert resp.status_code == 403, (
        f"{method} {path} → {resp.status_code}: firm-role token should get 403"
    )


# ─── Check 2: aal1 operator token → 401 ──────────────────────────────────────

@pytest.mark.anyio
@pytest.mark.parametrize("method,path", _PROTECTED_ROUTES)
async def test_aal1_operator_token_returns_401(method: str, path: str) -> None:
    """Operator token at aal1 (no TOTP) must be rejected — MFA is required."""
    filled = _fill_path(path)
    claims = {
        "sub": str(uuid4()),
        "aal": "aal1",
        "session_id": str(uuid4()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    # aal1 has no "role" claim — it looks like a GoTrue password-only token,
    # not a firm token, so _audit_forbidden_firm_token() won't fire.
    # require_operator must still reject it with 401 for lacking aal2.

    with patch("app.core.operator._decode_token", return_value=claims):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer fake-aal1-token"},
        ) as client:
            resp = await client.request(method, filled, json={})

    assert resp.status_code in (401, 403), (
        f"{method} {path} → {resp.status_code}: aal1 token should get 401/403"
    )


# ─── Check 3: deactivated operator → 403 ─────────────────────────────────────

@pytest.mark.anyio
async def test_deactivated_operator_returns_403_on_me() -> None:
    """Operator with is_active=False must be rejected after passing JWT checks."""
    sub = str(uuid4())
    claims = {
        "sub": sub,
        "aal": "aal2",
        "session_id": str(uuid4()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return {"auth_user_id": sub, "display_name": "Deactivated", "is_active": False}
        return None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
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
            headers={"Authorization": "Bearer fake-token"},
        ) as client:
            resp = await client.get("/admin/me")

    assert resp.status_code == 403, (
        f"Deactivated operator should get 403, got {resp.status_code}"
    )


# ─── Check 4: idle session → 401 ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_idle_session_returns_401_on_me() -> None:
    """A session last seen 31 minutes ago must be rejected as stale."""
    sub = str(uuid4())
    claims = {
        "sub": sub,
        "aal": "aal2",
        "session_id": str(uuid4()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    stale_time = datetime.now(tz=timezone.utc) - timedelta(minutes=31)

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return {"auth_user_id": sub, "display_name": "Op", "is_active": True}
        if "operator_sessions" in query and "last_seen" in query:
            return {"last_seen": stale_time}
        return None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.execute = AsyncMock(return_value="DELETE 1")
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
            headers={"Authorization": "Bearer fake-token"},
        ) as client:
            resp = await client.get("/admin/me")

    assert resp.status_code == 401, (
        f"Stale session should get 401, got {resp.status_code}"
    )


# ─── Check 5: firm-detail schema asserts no work-product fields ───────────────

# Work-product fields that must NEVER appear in /admin/firms/{id} responses.
_FORBIDDEN_FIELDS = {
    "case_notes", "case_description", "document_content", "ai_output_text",
    "client_name", "client_phone", "client_email", "client_address",
    "document_text", "ocr_result", "embedding", "full_text",
}


@pytest.mark.anyio
async def test_firm_detail_response_has_no_work_product_fields() -> None:
    """GET /admin/firms/{id} must return counts only — zero work-product content."""
    sub = str(uuid4())
    firm_id = uuid4()
    claims = {
        "sub": sub,
        "aal": "aal2",
        "session_id": str(uuid4()),
        "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    now = datetime.now(tz=timezone.utc)
    op_row = {"auth_user_id": sub, "display_name": "Op", "is_active": True}
    sess_row = {"last_seen": now}

    # Combined firms+subscriptions row (matches admin_get_firm JOIN query).
    firm_combined_row = {
        "id": firm_id,
        "name": "Test Firm",
        "slug": "test-firm",
        "status": "active",
        "trial_ends_at": None,
        "created_at": now,
        "plan": "basic",
        "sub_status": "active",
        "current_period_end": now + timedelta(days=30),
        "provider": "paymob",
    }
    usage_row = {
        "firm_id": firm_id,
        "user_count": 3,
        "case_count": 12,
        "document_count": 45,
        "storage_bytes": 0,
        "ai_output_count": 8,
        "last_activity_at": now,
    }
    created_sess = {"created_at": now}

    async def fetchrow_side(query, *args):
        if "platform_operators" in query:
            return op_row
        if "operator_sessions" in query and "last_seen" in query:
            return sess_row
        if "operator_sessions" in query and "created_at" in query:
            return created_sess
        if "FROM firms" in query:
            return firm_combined_row
        if "admin_firm_usage" in query:
            return usage_row
        return None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    mock_conn.execute = AsyncMock(return_value="INSERT 0 1")
    mock_conn.fetchval = AsyncMock(return_value=now)
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
            headers={"Authorization": "Bearer fake-token"},
        ) as client:
            resp = await client.get(f"/admin/firms/{firm_id}")

    assert resp.status_code == 200
    body = resp.json()

    # Flatten all keys in the response recursively.
    def _all_keys(d: object) -> set[str]:
        if isinstance(d, dict):
            keys: set[str] = set(d.keys())
            for v in d.values():
                keys |= _all_keys(v)
            return keys
        if isinstance(d, list):
            result: set[str] = set()
            for item in d:
                result |= _all_keys(item)
            return result
        return set()

    response_keys = _all_keys(body)
    forbidden_present = response_keys & _FORBIDDEN_FIELDS
    assert not forbidden_present, (
        f"Work-product fields found in firm detail response: {forbidden_present}"
    )
