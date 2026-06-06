"""Phase 6 smoke tests (T070) — deterministic deadlines/reminders/escalation.

Covers the constitutional + functional invariants of the scheduler (Component C):

  [C-IV]  Reminders are decided by deterministic CODE, never an LLM/agent.
          (verified structurally: the scheduler path imports no llm module.)
  FR-023/024  Reminders fire at the firm-configurable lead points.
  FR-025  Every send ATTEMPT writes a notifications_log row — including
          'failed' (send error) and 'skipped' (no phone / inactive); a
          reminder is never silently dropped.
  FR-024  Unacknowledged near-due deadlines escalate to a partner_manager.

Pure logic is unit-tested directly; ``run_reminders`` is exercised against a
fake connection + injected sender (no live DB).  Live-DB checks for quickstart
§7 are marked ``integration`` and skipped.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.scheduler.reminders import (
    FIRM_TZ,
    LeadPoint,
    build_deadline_message,
    build_escalation_message,
    build_task_message,
    matched_lead_point,
    parse_lead_points,
    run_reminders,
    should_escalate,
)
from app.scheduler.waha import WahaError, phone_to_chat_id

# ── lead point parsing (FR-023, firm-configurable) ───────────────────────────


def test_parse_lead_points_default_order() -> None:
    lps = parse_lead_points(["7d", "3d", "1d", "0d"])
    assert [lp.days for lp in lps] == [7, 3, 1, 0]  # sorted earliest-first


def test_parse_lead_points_from_json_string() -> None:
    # asyncpg may hand back a jsonb column as a string.
    lps = parse_lead_points('["3d", "1d"]')
    assert [lp.days for lp in lps] == [3, 1]


def test_parse_lead_points_falls_back_on_empty() -> None:
    assert [lp.days for lp in parse_lead_points([])] == [7, 3, 1, 0]
    assert [lp.days for lp in parse_lead_points(None)] == [7, 3, 1, 0]


def test_parse_lead_points_skips_garbage() -> None:
    lps = parse_lead_points(["3d", "oops", "1d"])
    assert [lp.days for lp in lps] == [3, 1]


def test_parse_lead_points_dedupes() -> None:
    lps = parse_lead_points(["3d", "3d", "1d"])
    assert [lp.days for lp in lps] == [3, 1]


# ── lead-point matching ──────────────────────────────────────────────────────

_LEADS = [LeadPoint("7d", 7), LeadPoint("3d", 3), LeadPoint("1d", 1), LeadPoint("0d", 0)]


def test_matched_lead_point_hits() -> None:
    today = date(2026, 6, 9)
    assert matched_lead_point(date(2026, 6, 12), today, _LEADS).days == 3  # 3 days out
    assert matched_lead_point(date(2026, 6, 9), today, _LEADS).days == 0  # same day


def test_matched_lead_point_miss() -> None:
    today = date(2026, 6, 9)
    assert matched_lead_point(date(2026, 6, 14), today, _LEADS) is None  # 5 days out
    assert matched_lead_point(date(2026, 6, 1), today, _LEADS) is None  # past


# ── escalation predicate (FR-024) ────────────────────────────────────────────


def test_should_escalate_unacknowledged_near_due() -> None:
    today = date(2026, 6, 9)
    assert should_escalate(date(2026, 6, 9), today, acknowledged=False) is True  # today
    assert should_escalate(date(2026, 6, 10), today, acknowledged=False) is True  # 1d


def test_should_not_escalate_when_acknowledged() -> None:
    today = date(2026, 6, 9)
    assert should_escalate(date(2026, 6, 9), today, acknowledged=True) is False


def test_should_not_escalate_when_far_out() -> None:
    today = date(2026, 6, 9)
    assert should_escalate(date(2026, 6, 13), today, acknowledged=False) is False  # 4d


# ── message builders (deterministic; Arabic) ─────────────────────────────────


def test_deadline_message_mentions_title_and_case() -> None:
    msg = build_deadline_message("جلسة", "قضية ١", date(2026, 6, 12), date(2026, 6, 9))
    assert "جلسة" in msg and "قضية ١" in msg and "2026-06-12" in msg


def test_escalation_message_names_responsible_lawyer() -> None:
    msg = build_escalation_message("جلسة", "قضية ١", date(2026, 6, 9), date(2026, 6, 9), "أ. محمد")
    assert "تصعيد" in msg and "أ. محمد" in msg


def test_task_message_built() -> None:
    msg = build_task_message("تجهيز المذكرة", "قضية ٢", date(2026, 6, 10), date(2026, 6, 9))
    assert "تجهيز المذكرة" in msg and "قضية ٢" in msg


# ── WAHA chatId normalization ────────────────────────────────────────────────


def test_phone_to_chat_id_strips_non_digits() -> None:
    assert phone_to_chat_id("+20 100 123 4567") == "201001234567@c.us"


# ── determinism guard [C-IV] ─────────────────────────────────────────────────


def test_scheduler_path_imports_no_llm() -> None:
    """The reminder path must never import an LLM module — reminders are
    deterministic [C-IV]."""
    import app.scheduler.reminders as r
    import app.scheduler.waha as w

    for mod in (r, w):
        src = mod.__file__
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        assert "app.llm" not in text, f"{src} must not import app.llm [C-IV]"


# ── run_reminders against a fake connection + injected sender ─────────────────


class FakeConn:
    """Minimal asyncpg-Connection stand-in routed by SQL substring."""

    def __init__(self, *, firm, partners=None, deadlines=None, tasks=None):
        self.firm = firm
        self.partners = partners or []
        self.deadlines = deadlines or []
        self.tasks = tasks or []
        self.inserts: list[dict] = []
        self._handled: set[tuple] = set()

    async def fetchrow(self, sql, *args):
        if "FROM firm_settings" in sql:
            return self.firm
        return None

    async def fetch(self, sql, *args):
        if "role = 'partner_manager'" in sql:
            return self.partners
        if "FROM deadlines" in sql:
            return self.deadlines
        if "FROM tasks" in sql:
            return self.tasks
        return []

    async def fetchval(self, sql, *args):
        # _already_handled EXISTS(...) — args are (deadline, task, recipient, lead, esc)
        return tuple(args) in self._handled

    async def execute(self, sql, *args):
        if "INSERT INTO notifications_log" not in sql:
            return
        row = {
            "deadline_id": args[0],
            "task_id": args[1],
            "recipient_user_id": args[2],
            "lead_point": args[3],
            "is_escalation": args[4],
            "scheduled_for": args[5],
            "sent_at": args[6],
            "status": args[7],
            "error_detail": args[8],
        }
        self.inserts.append(row)
        if row["status"] in ("sent", "skipped"):
            self._handled.add((args[0], args[1], args[2], args[3], args[4]))


def _firm(*, waha_url="https://waha.example", lead_points=None):
    return {
        "waha_url": waha_url,
        "waha_key": "secret-key",
        "reminder_lead_points": lead_points or ["7d", "3d", "1d", "0d"],
    }


def _deadline(*, responsible_id, due, acknowledged=False, phone="+201001234567", status="active"):
    return {
        "id": uuid4(),
        "title": "جلسة",
        "due_date": due,
        "acknowledged_at": datetime(2026, 6, 8, tzinfo=FIRM_TZ) if acknowledged else None,
        "responsible_user_id": responsible_id,
        "case_title": "قضية اختبار",
        "responsible_name": "أ. محمد",
        "responsible_phone": phone,
        "responsible_status": status,
    }


def _recording_sender():
    calls: list[dict] = []

    async def send(*, waha_url, waha_key, phone, text, session):
        calls.append({"phone": phone, "text": text})

    return send, calls


_NOW = datetime(2026, 6, 9, 9, 0, tzinfo=FIRM_TZ)  # 3 days before 2026-06-12


async def test_run_reminders_sends_once_and_is_idempotent() -> None:
    lawyer = uuid4()
    conn = FakeConn(firm=_firm(), deadlines=[_deadline(responsible_id=lawyer, due=date(2026, 6, 12))])
    send, calls = _recording_sender()

    s1 = await run_reminders(conn, now=_NOW, send=send)
    assert s1.sent == 1 and len(calls) == 1
    assert conn.inserts[0]["status"] == "sent"
    assert conn.inserts[0]["lead_point"] == "3d"

    # Second pass: identical attempt already 'sent' → deduped, no new send/insert.
    s2 = await run_reminders(conn, now=_NOW, send=send)
    assert s2.duplicate == 1 and s2.sent == 0
    assert len(calls) == 1  # no second send
    assert len(conn.inserts) == 1  # no new row


async def test_run_reminders_skips_recipient_without_phone() -> None:
    lawyer = uuid4()
    conn = FakeConn(
        firm=_firm(),
        deadlines=[_deadline(responsible_id=lawyer, due=date(2026, 6, 12), phone=None)],
    )
    send, calls = _recording_sender()

    summary = await run_reminders(conn, now=_NOW, send=send)
    assert summary.skipped == 1 and summary.sent == 0
    assert calls == []  # never attempted
    assert conn.inserts[0]["status"] == "skipped"  # but logged — never silently dropped


async def test_run_reminders_logs_failed_on_waha_error() -> None:
    lawyer = uuid4()
    conn = FakeConn(firm=_firm(), deadlines=[_deadline(responsible_id=lawyer, due=date(2026, 6, 12))])

    async def failing_send(*, waha_url, waha_key, phone, text, session):
        raise WahaError("boom")

    summary = await run_reminders(conn, now=_NOW, send=failing_send)
    assert summary.failed == 1
    assert conn.inserts[0]["status"] == "failed"
    assert "boom" in conn.inserts[0]["error_detail"]


async def test_escalation_to_partner_when_unacknowledged() -> None:
    lawyer = uuid4()
    partner = uuid4()
    # due tomorrow (1d) → primary reminder + escalation (unacknowledged, within window).
    now = datetime(2026, 6, 9, 9, 0, tzinfo=FIRM_TZ)
    conn = FakeConn(
        firm=_firm(),
        partners=[{"id": partner, "full_name": "شريك", "phone": "+201005550000", "status": "active"}],
        deadlines=[_deadline(responsible_id=lawyer, due=date(2026, 6, 10), acknowledged=False)],
    )
    send, calls = _recording_sender()

    summary = await run_reminders(conn, now=now, send=send)
    assert summary.sent == 2  # lawyer + partner
    escalations = [r for r in conn.inserts if r["is_escalation"]]
    assert len(escalations) == 1
    assert escalations[0]["recipient_user_id"] == partner


async def test_no_escalation_when_acknowledged() -> None:
    lawyer = uuid4()
    partner = uuid4()
    now = datetime(2026, 6, 9, 9, 0, tzinfo=FIRM_TZ)
    conn = FakeConn(
        firm=_firm(),
        partners=[{"id": partner, "full_name": "شريك", "phone": "+201005550000", "status": "active"}],
        deadlines=[_deadline(responsible_id=lawyer, due=date(2026, 6, 10), acknowledged=True)],
    )
    send, calls = _recording_sender()

    summary = await run_reminders(conn, now=now, send=send)
    assert summary.sent == 1  # lawyer only
    assert all(not r["is_escalation"] for r in conn.inserts)


# ── endpoint auth gates (ASGI, no live DB) ───────────────────────────────────

import httpx  # noqa: E402
import app.core.db as db_module  # noqa: E402
import unittest.mock as mock  # noqa: E402
from app.main import app  # noqa: E402


async def test_create_deadline_requires_auth() -> None:
    with mock.patch.object(db_module, "_pool", mock.AsyncMock()):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/cases/{uuid4()}/deadlines",
                json={"title": "x", "due_date": "2026-07-01", "responsible_user_id": str(uuid4())},
            )
    assert resp.status_code == 401


async def test_create_task_requires_auth() -> None:
    with mock.patch.object(db_module, "_pool", mock.AsyncMock()):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/cases/{uuid4()}/tasks",
                json={"description": "x", "assigned_to": str(uuid4())},
            )
    assert resp.status_code == 401


# ── integration (live DB) — quickstart §7 ────────────────────────────────────


@pytest.mark.integration
async def test_reminder_delivery_and_escalation_live() -> None:  # pragma: no cover
    """quickstart §7: confirmed deadline → WhatsApp reminder + notifications_log
    row; partner escalation when unacknowledged.

    Requires a provisioned instance with firm_settings.waha_url/key set and a
    WAHA session. Run the scheduler once:  python -m workers.scheduler_worker --once
    """
    pytest.skip("Requires live DB + WAHA session — see quickstart.md §7")
