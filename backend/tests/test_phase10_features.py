"""Phase 7/10/11/12 smoke tests — US5 scaffold, US6 inbound, US7/8/9 features.

Covers the constitution-critical guarantees of the newly added features without a
live DB or network:

  [C-X]  US5 appeal calc is INERT — no periods are hard-coded; suggestions are
         empty until expert sign-off.
  [C-I]  US6 inbound binds sender phone → active user; unknown/inactive resolve to
         None (→ refusal, no case content). Webhook token gate rejects bad tokens.
  [C-IX] US8 reference results are framed persuasive-only / not-binding.
  Auth   US7/US8/US9 generation+search endpoints require authentication.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import httpx
import pytest
import unittest.mock as mock

import app.core.db as db_module
from app.main import app


# ── US5: appeal scaffold is inert until expert sign-off [C-X] ─────────────────

from app.scheduler.appeal_deadlines import APPEAL_PERIODS_DAYS, suggest_appeal_deadlines


def test_appeal_periods_empty_pending_signoff() -> None:
    assert APPEAL_PERIODS_DAYS == {}  # no fabricated legal periods [C-X]


def test_appeal_suggestions_empty_until_periods_blessed() -> None:
    out = suggest_appeal_deadlines(date(2026, 1, 1), responsible_user_id=uuid4())
    assert out == []


# ── US6: sender phone → identity binding [C-I] ────────────────────────────────

from app.api.assistant import _digits, _resolve_active_user


class _RowConn:
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, sql, *args):
        return self._row


def test_digits_strips_non_digits() -> None:
    assert _digits("+20 100 123 4567") == "201001234567"
    assert _digits(None) == ""


async def test_resolve_rejects_unknown_sender() -> None:
    assert await _resolve_active_user(_RowConn(None), "201001234567") is None


async def test_resolve_rejects_inactive_user() -> None:
    row = {
        "id": uuid4(), "auth_user_id": uuid4(), "full_name": "س", "email": "e@x.co",
        "phone": "+201001234567", "role": "lawyer", "status": "inactive",
    }
    assert await _resolve_active_user(_RowConn(row), "201001234567") is None


async def test_resolve_accepts_active_user() -> None:
    row = {
        "id": uuid4(), "auth_user_id": uuid4(), "full_name": "س", "email": "e@x.co",
        "phone": "+201001234567", "role": "lawyer", "status": "active",
    }
    user = await _resolve_active_user(_RowConn(row), "201001234567")
    assert user is not None and user.role == "lawyer"


async def test_webhook_rejects_bad_token() -> None:
    fake_settings = mock.Mock(waha_webhook_token="s3cret", waha_session="default")
    with mock.patch("app.api.assistant.get_settings", return_value=fake_settings):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/assistant/whatsapp/webhook",
                headers={"X-Webhook-Token": "wrong"},
                json={"event": "message", "payload": {"from": "201@c.us", "body": "hi"}},
            )
    assert resp.status_code == 401


async def test_webhook_ignores_own_messages() -> None:
    # No token configured → token gate passes; fromMe short-circuits before any DB.
    fake_settings = mock.Mock(waha_webhook_token="", waha_session="default")
    with mock.patch("app.api.assistant.get_settings", return_value=fake_settings):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/assistant/whatsapp/webhook",
                json={"event": "message", "payload": {"fromMe": True, "from": "201@c.us", "body": "x"}},
            )
    assert resp.status_code == 200 and resp.json()["status"] == "ignored"


# ── US8: persuasive-only framing [C-IX] ───────────────────────────────────────

from app.retriever.references import PERSUASIVE_ONLY_NOTICE


def test_reference_notice_is_persuasive_only() -> None:
    assert "مُلزِمة" in PERSUASIVE_ONLY_NOTICE  # explicitly "not binding"
    assert "تنبؤاً" in PERSUASIVE_ONLY_NOTICE   # explicitly "not a prediction"


# ── US7/US8/US9 endpoints require auth ────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", f"/documents/{uuid4()}/analyze-contract", None),
        ("POST", f"/documents/{uuid4()}/risk-signals", None),
        ("POST", "/references/search", {"query": "عقد"}),
    ],
)
async def test_generation_endpoints_require_auth(method, path, body) -> None:
    with mock.patch.object(db_module, "_pool", mock.AsyncMock()):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.request(method, path, json=body)
    assert resp.status_code == 401
