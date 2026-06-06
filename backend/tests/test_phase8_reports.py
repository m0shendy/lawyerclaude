"""Phase 8 smoke tests (T075) — deterministic daily reports (Component C). [C-IV]

Covers:
  [C-IV]  Report assembly is deterministic; the LLM is used for *phrasing only*
          and is never imported at the selection path's module top level.
  T071    "What happened" items reconcile to audited data — every such item
          carries the ``audit_id`` of the ``audit_log`` row it came from, and the
          assembler emits nothing that isn't backed by a returned row.
  T072    Phrasing degrades to deterministic prose without an LLM key.
  Auth    ``GET /reports/daily`` is manager-gated (401 unauthenticated).

Pure logic is exercised against a fake connection (SQL routed by substring); the
endpoint auth gate runs over ASGI with a mocked pool (no live DB).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.scheduler.reports import (
    FIRM_TZ,
    ReportItem,
    assemble_daily_report,
    phrase_section,
)

_NOW = datetime(2026, 6, 6, 9, 0, tzinfo=FIRM_TZ)
_AUDIT_TS = datetime(2026, 6, 6, 8, 30, tzinfo=FIRM_TZ)


class FakeConn:
    """Minimal asyncpg-Connection stand-in routed by SQL substring."""

    def __init__(self, *, cases=None, tomorrow_tasks=None):
        self._cases = cases or []
        self._tomorrow_tasks = tomorrow_tasks or []

    async def fetch(self, sql, *args):
        if "audit_log a JOIN cases c" in sql:
            return self._cases
        if "JOIN documents d ON d.id = a.record_id" in sql:
            return []
        if "JOIN deadlines d ON d.id = a.record_id" in sql:
            return []
        if "JOIN tasks t ON t.id = a.record_id" in sql:
            return []
        if "JOIN ai_outputs o" in sql:
            return []
        if "d.confirmed = true" in sql:  # tomorrow deadlines
            return []
        if "t.status IN ('open', 'in_progress')" in sql:  # tomorrow tasks
            return self._tomorrow_tasks
        return []


def _case_audit_row(audit_id: int):
    return {
        "audit_id": audit_id,
        "action": "insert",
        "when_ts": _AUDIT_TS,
        "title": "قضية اختبار",
        "client_name": "عميل",
    }


def _tomorrow_task_row():
    return {
        "id": uuid4(),
        "description": "تجهيز مذكرة",
        "due_date": date(2026, 6, 7),
        "case_title": "قضية اختبار",
        "assignee": "أ. محمد",
    }


# ── reconciliation: items ↔ audited data (T071/T075) ─────────────────────────


async def test_what_happened_items_reconcile_to_audit_rows() -> None:
    conn = FakeConn(cases=[_case_audit_row(101), _case_audit_row(102)])
    report = await assemble_daily_report(conn, now=_NOW)

    # Exactly the two audited events — nothing invented.
    assert len(report.what_happened) == 2
    # Every "what happened" item is grounded in an audit_log row.
    assert {it.audit_id for it in report.what_happened} == {101, 102}
    assert all(it.audit_id is not None for it in report.what_happened)


async def test_tomorrow_items_reference_live_rows() -> None:
    task_row = _tomorrow_task_row()
    conn = FakeConn(tomorrow_tasks=[task_row])
    report = await assemble_daily_report(conn, now=_NOW)

    assert len(report.tomorrow) == 1
    item = report.tomorrow[0]
    assert item.kind == "task_due"
    assert item.ref_table == "tasks"
    assert item.ref_id == str(task_row["id"])
    assert item.audit_id is None  # upcoming, not an audit event


async def test_empty_day_yields_empty_report() -> None:
    report = await assemble_daily_report(FakeConn(), now=_NOW)
    assert report.what_happened == []
    assert report.tomorrow == []
    assert report.report_date == date(2026, 6, 6)


# ── phrasing-only fallback (T072) ─────────────────────────────────────────────


async def test_phrase_section_falls_back_without_key() -> None:
    items = [ReportItem(kind="case_insert", title="قضية «أ» أُضيفت", audit_id=1)]
    prose = await phrase_section("ما حدث اليوم", items, api_key=None, model="m")
    assert "قضية «أ» أُضيفت" in prose  # deterministic prose carries the facts


async def test_phrase_section_empty_items() -> None:
    prose = await phrase_section("مهام الغد", [], api_key="key", model="m")
    assert "لا يوجد" in prose  # no LLM call attempted for an empty section


# ── determinism guard [C-IV] ─────────────────────────────────────────────────


def test_assembly_path_does_not_import_llm_at_module_level() -> None:
    """The LLM must only be reachable through the phrasing step, imported lazily
    inside ``phrase_section`` — never at the selection path's module top. [C-IV]"""
    import app.scheduler.reports as r

    # generate is imported lazily inside phrase_section, so it must NOT be a
    # module-level attribute of the reports module.
    assert not hasattr(r, "generate")


# ── endpoint auth gate (ASGI, no live DB) ─────────────────────────────────────

import httpx  # noqa: E402
import unittest.mock as mock  # noqa: E402

import app.core.db as db_module  # noqa: E402
from app.main import app  # noqa: E402


async def test_daily_report_requires_auth() -> None:
    with mock.patch.object(db_module, "_pool", mock.AsyncMock()):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/reports/daily")
    assert resp.status_code == 401
