"""Phase 9 smoke tests — scoped conversational assistant. [C-I][C-II]

Covers:
  [C-I]   Retrieval scope: managers see all cases (no filter); non-managers are
          restricted to their ``case_assignments``. An explicit out-of-scope
          ``case_id`` yields nothing — and short-circuits *before* any embedding
          call, so no document is ever read for a case the caller can't access.
  Auth    ``POST /assistant/query`` requires authentication (401).

Logic runs against a fake connection; the auth gate runs over ASGI with a mocked
pool (no live DB, no network).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.security import CurrentUser
from app.retriever.scoped import accessible_case_ids, retrieve_scoped


def _user(role: str, user_id=None) -> CurrentUser:
    return CurrentUser(
        id=user_id or uuid4(),
        auth_user_id=uuid4(),
        full_name="مستخدم",
        email="u@example.com",
        phone=None,
        role=role,  # type: ignore[arg-type]
        status="active",
    )


class FakeConn:
    """Routes the case_assignments lookup; fails loudly if anything else runs."""

    def __init__(self, assigned_case_ids):
        self._assigned = [{"case_id": cid} for cid in assigned_case_ids]
        self.fetch_calls: list[str] = []

    async def fetch(self, sql, *args):
        self.fetch_calls.append(sql)
        if "FROM case_assignments WHERE user_id" in sql:
            return self._assigned
        raise AssertionError(f"unexpected query in scope check: {sql!r}")


# ── scope resolution [C-I] ────────────────────────────────────────────────────


async def test_manager_scope_is_all_cases() -> None:
    assert await accessible_case_ids(FakeConn([]), _user("partner_manager")) is None


async def test_non_manager_scope_lists_assignments() -> None:
    cid = uuid4()
    allowed = await accessible_case_ids(FakeConn([cid]), _user("lawyer"))
    assert allowed == [cid]


async def test_retrieve_scoped_out_of_scope_returns_empty_without_embedding() -> None:
    """A lawyer asking about a case they aren't assigned to gets nothing — and we
    never reach the embedding/SQL stage (FakeConn would raise if we did)."""
    assigned = uuid4()
    other = uuid4()
    conn = FakeConn([assigned])

    chunks = await retrieve_scoped(
        "سؤال",
        conn=conn,
        user=_user("lawyer"),
        api_key="",                 # must not be used — no embedding happens
        embedding_config={},
        case_id=other,              # out of scope
        top_k=8,
    )
    assert chunks == []
    # Only the scope lookup ran; no embedding/vector query was attempted.
    assert len(conn.fetch_calls) == 1


# ── endpoint auth gate (ASGI, no live DB) ─────────────────────────────────────

import httpx  # noqa: E402
import unittest.mock as mock  # noqa: E402

import app.core.db as db_module  # noqa: E402
from app.main import app  # noqa: E402


async def test_assistant_query_requires_auth() -> None:
    with mock.patch.object(db_module, "_pool", mock.AsyncMock()):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/assistant/query", json={"query": "مرحبا"})
    assert resp.status_code == 401
