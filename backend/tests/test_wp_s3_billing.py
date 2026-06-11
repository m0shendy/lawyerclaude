"""WP-S3 billing + signup unit tests.

Covers the security-critical pure logic:
  * Paymob HMAC verification (valid / tampered / missing secret)
  * amount reconciliation against the PLANS table
  * slug generation
  * trial expiry SQL shape (FakeConn)
No network, no DB — live webhook flow is exercised on a provisioned instance.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod

import pytest

from app.billing import PLANS
from app.billing.paymob import _HMAC_FIELDS, _dig, _to_hmac_str, reconcile_amount, verify_webhook_hmac
from app.api.signup import _slugify

_SECRET = "test-hmac-secret"


def _make_payload(**overrides):
    obj = {
        "amount_cents": 150000,
        "created_at": "2026-06-10T12:00:00",
        "currency": "EGP",
        "error_occured": False,
        "has_parent_transaction": False,
        "id": 987654,
        "integration_id": 11111,
        "is_3d_secure": True,
        "is_auth": False,
        "is_capture": False,
        "is_refunded": False,
        "is_standalone_payment": True,
        "is_voided": False,
        "order": {"id": 555},
        "owner": 1,
        "pending": False,
        "source_data": {"pan": "1234", "sub_type": "MasterCard", "type": "card"},
        "success": True,
    }
    obj.update(overrides)
    return obj


def _sign(obj) -> str:
    concat = "".join(_to_hmac_str(_dig(obj, f)) for f in _HMAC_FIELDS)
    return hmac_mod.new(_SECRET.encode(), concat.encode(), hashlib.sha512).hexdigest()


@pytest.fixture(autouse=True)
def _paymob_secret(monkeypatch):
    from app.core import config

    config.get_settings.cache_clear() if hasattr(config.get_settings, "cache_clear") else None
    monkeypatch.setenv("PAYMOB_HMAC_SECRET", _SECRET)
    yield
    if hasattr(config.get_settings, "cache_clear"):
        config.get_settings.cache_clear()


def test_hmac_valid_payload_verifies():
    obj = _make_payload()
    assert verify_webhook_hmac(obj, _sign(obj)) is True


def test_hmac_tampered_amount_rejected():
    obj = _make_payload()
    sig = _sign(obj)
    obj["amount_cents"] = 1  # attacker pays 1 cent, replays signature
    assert verify_webhook_hmac(obj, sig) is False


def test_hmac_tampered_success_flag_rejected():
    obj = _make_payload(success=False)
    sig = _sign(obj)
    obj["success"] = True
    assert verify_webhook_hmac(obj, sig) is False


def test_hmac_missing_or_empty_rejected():
    obj = _make_payload()
    assert verify_webhook_hmac(obj, "") is False
    assert verify_webhook_hmac(obj, "deadbeef") is False


def test_reconcile_amount_matches_plan_table():
    assert reconcile_amount("basic", PLANS["basic"].monthly_egp * 100) is True
    assert reconcile_amount("basic", PLANS["basic"].monthly_egp * 100 - 1) is False
    assert reconcile_amount("pro", PLANS["basic"].monthly_egp * 100) is False
    assert reconcile_amount("unknown", 100) is False
    assert reconcile_amount("basic", "not-a-number") is False


def test_slugify_arabic_and_spacing():
    assert _slugify("Shendy & Partners  LLP") == "shendy-partners-llp"
    # Arabic-only names degrade to the fallback rather than an empty slug.
    assert _slugify("مكتب الشندي للمحاماة") == "firm"
    assert len(_slugify("x" * 200)) <= 40


@pytest.mark.asyncio
async def test_expire_trials_sql_shape():
    from app.scheduler.reminders import expire_trials

    captured: dict = {}

    class FakeConn:
        async def fetch(self, sql, *args):
            captured["sql"] = sql
            return [{"id": 1}, {"id": 2}]

    n = await expire_trials(FakeConn())
    assert n == 2
    sql = captured["sql"]
    # Must only suspend lapsed trials WITHOUT an active subscription.
    assert "status = 'trial'" in sql
    assert "trial_ends_at < now()" in sql
    assert "NOT EXISTS" in sql and "s.status = 'active'" in sql
