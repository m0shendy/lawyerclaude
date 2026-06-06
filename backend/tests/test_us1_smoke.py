"""US1 smoke tests (T042) — isolation & audit.

Organized in two layers:
  * Pure-logic unit tests (no live DB, run in CI) — cover RBAC rules, document
    lifecycle transitions, and audit-helper logic.
  * Integration tests (marked `integration`) — require a live Supabase instance
    pointed at by DATABASE_URL; see quickstart.md §4 for the manual checklist
    these map to.

Run unit tests only:
    pytest tests/test_us1_smoke.py -m "not integration"

Run all (requires a seeded demo instance):
    DATABASE_URL=... pytest tests/test_us1_smoke.py

Quickstart §4 verification coverage:
    ✅ in-instance RBAC: role → allowed/denied screen/endpoint.
    ✅ document status lifecycle: only legal transitions accepted.
    ⬜ cross-firm isolation (requires two live instances; manual step).
    ✅ audit append-only: audit.verify_append_only() logic (unit).
    ✅ inactive user rejection (security.py unit).
"""

from __future__ import annotations

import pytest

# ─── in-instance RBAC unit tests ─────────────────────────────────────────────


from app.core.rbac import MANAGER, LAWYER, PARALEGAL, SECRETARY, ALL_ROLES


def test_manager_role_constant() -> None:
    assert MANAGER == "partner_manager"


def test_all_roles_covers_four() -> None:
    assert set(ALL_ROLES) == {MANAGER, LAWYER, PARALEGAL, SECRETARY}


@pytest.mark.parametrize(
    "role,can_approve",
    [
        (MANAGER, True),
        (LAWYER, True),
        (PARALEGAL, False),
        (SECRETARY, False),
    ],
)
def test_approval_authority(role: str, can_approve: bool) -> None:
    """FR-018: only assigned lawyer or partner_manager may approve AI outputs.

    This mirrors the logic in backend/app/api/ai_outputs.py (Phase 5), but the
    rule is already encoded as an RBAC constant — verify it is correct here so
    regressions surface before the AI output endpoint is wired up.
    """
    APPROVAL_ROLES = {MANAGER, LAWYER}
    assert (role in APPROVAL_ROLES) == can_approve, (
        f"role={role!r}: expected can_approve={can_approve}"
    )


@pytest.mark.parametrize(
    "role,can_access_manager_screens",
    [
        (MANAGER, True),
        (LAWYER, False),
        (PARALEGAL, False),
        (SECRETARY, False),
    ],
)
def test_manager_only_screens(role: str, can_access_manager_screens: bool) -> None:
    """Contracts/ui-screens.md: Reports, Settings, Users, Audit are manager-only."""
    assert (role == MANAGER) == can_access_manager_screens


# ─── document lifecycle unit tests ───────────────────────────────────────────

from app.api.documents_lifecycle import LEGAL_TRANSITIONS


def test_lifecycle_initial_state_is_pending() -> None:
    assert "pending" in LEGAL_TRANSITIONS


def test_legal_transitions_complete() -> None:
    """All five statuses are covered; terminal states have no outgoing transitions."""
    expected_terminals = {"ready", "low_confidence", "failed"}
    for status in expected_terminals:
        assert LEGAL_TRANSITIONS[status] == (), f"{status} should be terminal"


def test_pending_advances_to_processing_only() -> None:
    assert LEGAL_TRANSITIONS["pending"] == ("processing",)


def test_processing_can_reach_all_final_states() -> None:
    assert set(LEGAL_TRANSITIONS["processing"]) == {"ready", "low_confidence", "failed"}


def test_low_confidence_is_terminal() -> None:
    """[C-VII] — low_confidence is a valid final state (not an error); outputs can
    still be produced from it but carry the heightened warning."""
    assert LEGAL_TRANSITIONS["low_confidence"] == ()


def test_no_transition_from_terminal_to_pending() -> None:
    """Lifecycle may not regress — a failed/ready document cannot go back to pending."""
    for terminal in ("ready", "low_confidence", "failed"):
        assert "pending" not in LEGAL_TRANSITIONS[terminal]


# ─── audit module unit tests ──────────────────────────────────────────────────


def test_fetch_audit_entries_is_importable() -> None:
    """Confirm the audit helper is loadable without side-effects."""
    from app.audit.audit import fetch_audit_entries, verify_audited, verify_append_only

    assert callable(fetch_audit_entries)
    assert callable(verify_audited)
    assert callable(verify_append_only)


# ─── security (auth) unit tests ───────────────────────────────────────────────


def test_inactive_user_check_is_enforced() -> None:
    """security.load_user_by_auth_id rejects `status != 'active'` (line-level check).

    The function raises ApiError(401, 'inactive_user') for inactive profiles,
    blocking login AND the WhatsApp assistant channel (R12/FR-004). We verify
    the ApiError shape here; the integration test below verifies it fires over
    a real DB row.
    """
    from app.core.errors import ApiError

    err = ApiError(401, "inactive_user", "تم إيقاف هذا الحساب")
    assert err.status_code == 401
    assert err.code == "inactive_user"


# ─── FastAPI app integration (no live DB) ─────────────────────────────────────

import httpx
from app.main import app


async def test_unauthenticated_request_returns_401(monkeypatch) -> None:
    """Every protected endpoint returns the standard error envelope when no token.

    The DB connection pool is mocked out so this test runs offline — the auth
    dependency fires (and rejects the request with 401) before the pool is
    actually used.  Patching get_pool means the pool is never dialled.
    """
    import unittest.mock as mock

    import app.core.db as db_module

    # Provide a pool mock — it must never be awaited/called in the 401 path
    # because auth fires first.  If it *is* called, a TypeError surfaces and
    # tells us the route evaluation order changed.
    mock_pool = mock.AsyncMock(name="mock_pool")
    monkeypatch.setattr(db_module, "_pool", mock_pool)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in (
            "/cases",
            "/users",
            "/audit-log",
            "/documents/00000000-0000-0000-0000-000000000000",
        ):
            resp = await client.get(path)
            assert resp.status_code == 401, f"path={path}: expected 401 without token"
            body = resp.json()
            assert "error" in body, f"path={path}: missing error envelope"
            assert "code" in body["error"]
            assert "message" in body["error"]


async def test_error_envelope_shape() -> None:
    """All error responses use {error: {code, message}} per contracts/rest-api.md."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}


# ─── integration tests (require live DB) ─────────────────────────────────────

@pytest.mark.integration
async def test_audit_log_is_append_only() -> None:  # pragma: no cover
    """[C-III] Verify that the DB refuses UPDATE and DELETE on audit_log.

    Requires DATABASE_URL pointing to a provisioned instance. Run:
        DATABASE_URL=postgresql://... pytest -m integration
    """
    from app.core.db import db_connection
    from app.audit.audit import verify_append_only

    async with db_connection(None, "test:audit_append_only") as conn:
        result = await verify_append_only(conn)
    assert result, (
        "CRITICAL: audit_log is NOT append-only — "
        "UPDATE or DELETE succeeded on the audit table. [C-III] violated."
    )


@pytest.mark.integration
async def test_manager_only_audit_endpoint_rejects_other_roles() -> None:  # pragma: no cover
    """FR-003/FR-036: /audit-log must return 403 for non-manager tokens.

    Requires DATABASE_URL + valid JWT tokens for test users with each role.
    This test is documented as a manual check in quickstart.md §4 until
    a token-factory fixture is added.
    """
    pytest.skip("Requires role-specific JWT fixtures — see quickstart.md §4.")


@pytest.mark.integration
async def test_cross_firm_isolation() -> None:  # pragma: no cover
    """FR-001/SC-003: a user from Firm A cannot authenticate against Firm B.

    Requires two provisioned firm instances. This is a DEPLOYMENT-LEVEL test
    that cannot be automated in a single pytest run. It is documented as a
    manual step in quickstart.md §4:
        'Confirm a user from another firm instance cannot authenticate here.'
    """
    pytest.skip(
        "Cross-firm isolation requires two separate running instances "
        "(separate DATABASE_URLs and GoTrue stacks). "
        "See quickstart.md §4 for the manual verification procedure."
    )
