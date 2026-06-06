"""Deterministic daily report assembly — Component C (T071, T072, T073). [C-IV]

Reports, like reminders, are **deterministic code, never agentic** [C-IV]. The
split here is strict:

  * ``assemble_daily_report`` (T071) — pure SELECTs over **already-audited data**.
    "What happened today" items are read straight from ``audit_log`` (the
    append-only change history); each item carries the ``audit_id`` it came from,
    so the report provably *reconciles to audited data* and cannot invent events.
    "Tomorrow's tasks" are the deadlines/tasks actually due tomorrow.
  * ``phrase_section`` (T072) — an LLM **phrasing-only** step. It rewords the
    code-selected facts into Arabic prose. It is given the facts as a closed list
    and instructed it may not add, omit, or select. If the LLM key is missing or
    the call fails, we fall back to deterministic prose — the *items* remain the
    source of truth, the prose is cosmetic.
  * ``generate_and_send_daily_reports`` (T073) — assemble → phrase → WAHA send to
    each manager → write a ``reports_log`` row per section.

This module must never let the LLM decide *which* facts appear. The determinism
guard test asserts the selection path imports no agent logic.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg

logger = logging.getLogger(__name__)

# Firm-local day boundary (Egypt) — same convention as the reminder scheduler.
FIRM_TZ = ZoneInfo("Africa/Cairo")

Sender = Callable[..., Awaitable[None]]


# ── report item ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReportItem:
    """One code-selected fact. ``audit_id`` ties a "what happened" item back to
    the exact ``audit_log`` row it was derived from (reconciliation key, T075).
    ``ref_table``/``ref_id`` tie a "tomorrow" item to its live row."""

    kind: str               # e.g. "case_insert", "deadline_due", "task_due"
    title: str              # human Arabic label
    audit_id: int | None = None
    ref_table: str | None = None
    ref_id: str | None = None
    case_title: str | None = None
    when: str | None = None  # ISO timestamp/date for ordering on the client

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class DailyReport:
    report_date: date
    what_happened: list[ReportItem] = field(default_factory=list)
    tomorrow: list[ReportItem] = field(default_factory=list)


# ── assembly (deterministic; T071) ────────────────────────────────────────────

# Entity tables whose audited changes are worth surfacing in the daily digest.
_WHAT_HAPPENED_TABLES = ("cases", "documents", "deadlines", "tasks", "ai_outputs")

_ACTION_AR = {"create": "أُضيف", "update": "حُدّث", "delete": "حُذف"}


async def assemble_daily_report(
    conn: asyncpg.Connection, *, now: datetime | None = None
) -> DailyReport:
    """Build today's report from audited data only. Pure selection — no LLM.

    "What happened" = audit_log rows stamped today (firm tz), joined to their
    still-present entity row for a human title. "Tomorrow" = confirmed deadlines
    and open tasks whose due_date is tomorrow.
    """
    now = now or datetime.now(tz=FIRM_TZ)
    today = now.astimezone(FIRM_TZ).date()
    start = datetime.combine(today, time.min, tzinfo=FIRM_TZ)
    end = start + timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    report = DailyReport(report_date=today)

    # ── what happened today (grounded in audit_log) ──────────────────────────
    # cases
    for r in await conn.fetch(
        """
        SELECT a.id AS audit_id, a.action::text AS action, a.when_ts,
               c.title, c.client_name
        FROM audit_log a JOIN cases c ON c.id = a.record_id
        WHERE a.entity_table = 'cases' AND a.when_ts >= $1 AND a.when_ts < $2
        ORDER BY a.when_ts
        """,
        start, end,
    ):
        report.what_happened.append(
            ReportItem(
                kind=f"case_{r['action']}",
                title=f"قضية «{r['title']}» ({r['client_name']}) {_ACTION_AR.get(r['action'], r['action'])}",
                audit_id=r["audit_id"],
                ref_table="cases",
                when=r["when_ts"].isoformat(),
            )
        )

    # documents
    for r in await conn.fetch(
        """
        SELECT a.id AS audit_id, a.action::text AS action, a.when_ts,
               d.file_name, c.title AS case_title
        FROM audit_log a
        JOIN documents d ON d.id = a.record_id
        JOIN cases c ON c.id = d.case_id
        WHERE a.entity_table = 'documents' AND a.when_ts >= $1 AND a.when_ts < $2
        ORDER BY a.when_ts
        """,
        start, end,
    ):
        report.what_happened.append(
            ReportItem(
                kind=f"document_{r['action']}",
                title=f"مستند «{r['file_name']}» {_ACTION_AR.get(r['action'], r['action'])}",
                audit_id=r["audit_id"],
                ref_table="documents",
                case_title=r["case_title"],
                when=r["when_ts"].isoformat(),
            )
        )

    # deadlines
    for r in await conn.fetch(
        """
        SELECT a.id AS audit_id, a.action::text AS action, a.when_ts,
               d.title, c.title AS case_title
        FROM audit_log a
        JOIN deadlines d ON d.id = a.record_id
        JOIN cases c ON c.id = d.case_id
        WHERE a.entity_table = 'deadlines' AND a.when_ts >= $1 AND a.when_ts < $2
        ORDER BY a.when_ts
        """,
        start, end,
    ):
        report.what_happened.append(
            ReportItem(
                kind=f"deadline_{r['action']}",
                title=f"موعد «{r['title']}» {_ACTION_AR.get(r['action'], r['action'])}",
                audit_id=r["audit_id"],
                ref_table="deadlines",
                case_title=r["case_title"],
                when=r["when_ts"].isoformat(),
            )
        )

    # tasks
    for r in await conn.fetch(
        """
        SELECT a.id AS audit_id, a.action::text AS action, a.when_ts,
               t.description, c.title AS case_title
        FROM audit_log a
        JOIN tasks t ON t.id = a.record_id
        JOIN cases c ON c.id = t.case_id
        WHERE a.entity_table = 'tasks' AND a.when_ts >= $1 AND a.when_ts < $2
        ORDER BY a.when_ts
        """,
        start, end,
    ):
        report.what_happened.append(
            ReportItem(
                kind=f"task_{r['action']}",
                title=f"مهمة «{r['description']}» {_ACTION_AR.get(r['action'], r['action'])}",
                audit_id=r["audit_id"],
                ref_table="tasks",
                case_title=r["case_title"],
                when=r["when_ts"].isoformat(),
            )
        )

    # ai_outputs (notably approvals — the review gate clearing)
    for r in await conn.fetch(
        """
        SELECT a.id AS audit_id, a.action::text AS action, a.when_ts,
               o.type::text AS type, o.review_state::text AS review_state
        FROM audit_log a JOIN ai_outputs o ON o.id = a.record_id
        WHERE a.entity_table = 'ai_outputs' AND a.when_ts >= $1 AND a.when_ts < $2
        ORDER BY a.when_ts
        """,
        start, end,
    ):
        verb = (
            "اعتُمد"
            if r["action"] == "update" and r["review_state"] == "approved"
            else _ACTION_AR.get(r["action"], r["action"])
        )
        report.what_happened.append(
            ReportItem(
                kind=f"ai_output_{r['action']}",
                title=f"مخرج ذكاء اصطناعي ({r['type']}) {verb}",
                audit_id=r["audit_id"],
                ref_table="ai_outputs",
                when=r["when_ts"].isoformat(),
            )
        )

    report.what_happened.sort(key=lambda it: it.when or "")

    # ── tomorrow's obligations (live, deterministic) ─────────────────────────
    for r in await conn.fetch(
        """
        SELECT d.id, d.title, d.due_date, c.title AS case_title,
               u.full_name AS responsible
        FROM deadlines d
        JOIN cases c ON c.id = d.case_id
        JOIN users u ON u.id = d.responsible_user_id
        WHERE d.confirmed = true AND d.due_date = $1
        ORDER BY c.title
        """,
        tomorrow,
    ):
        report.tomorrow.append(
            ReportItem(
                kind="deadline_due",
                title=f"موعد «{r['title']}» مستحق غدًا — المسؤول: {r['responsible']}",
                ref_table="deadlines",
                ref_id=str(r["id"]),
                case_title=r["case_title"],
                when=r["due_date"].isoformat(),
            )
        )

    for r in await conn.fetch(
        """
        SELECT t.id, t.description, t.due_date, c.title AS case_title,
               u.full_name AS assignee
        FROM tasks t
        JOIN cases c ON c.id = t.case_id
        JOIN users u ON u.id = t.assigned_to
        WHERE t.status IN ('open', 'in_progress') AND t.due_date = $1
        ORDER BY c.title
        """,
        tomorrow,
    ):
        report.tomorrow.append(
            ReportItem(
                kind="task_due",
                title=f"مهمة «{r['description']}» مستحقة غدًا — المكلَّف: {r['assignee']}",
                ref_table="tasks",
                ref_id=str(r["id"]),
                case_title=r["case_title"],
                when=r["due_date"].isoformat(),
            )
        )

    return report


# ── deterministic prose fallback ──────────────────────────────────────────────


def _deterministic_prose(heading: str, items: list[ReportItem]) -> str:
    if not items:
        return f"{heading}: لا يوجد."
    lines = "\n".join(f"• {it.title}" for it in items)
    return f"{heading}:\n{lines}"


# ── LLM phrasing-only step (T072) ─────────────────────────────────────────────

_PHRASING_INSTRUCTION = (
    "أعد صياغة الحقائق التالية في فقرة عربية موجزة ومهنية تحت العنوان المذكور. "
    "هذه قائمة مغلقة: لا تُضِف أي معلومة، ولا تحذف أي بند، ولا تستنتج شيئًا غير "
    "مذكور فيها. اكتفِ بإعادة الصياغة فقط.\n\n"
)


async def phrase_section(
    heading: str,
    items: list[ReportItem],
    *,
    api_key: str | None,
    model: str,
) -> str:
    """Reword *items* into Arabic prose. Phrasing only — never adds/omits/selects.

    Falls back to deterministic prose when no API key is configured or the LLM
    call fails. The items remain authoritative regardless. [C-IV]
    """
    if not items or not api_key:
        return _deterministic_prose(heading, items)

    # Imported here so the deterministic selection path (assemble_daily_report)
    # never transitively imports the LLM module. [C-IV]
    from app.llm.generate import LlmError, generate

    facts = "\n".join(f"- {it.title}" for it in items)
    prompt = f"{_PHRASING_INSTRUCTION}العنوان: {heading}\n\nالحقائق:\n{facts}"
    try:
        return await generate(prompt, api_key=api_key, model=model, temperature=0.1)
    except LlmError as exc:
        logger.warning("reports: phrasing failed, using deterministic prose: %s", exc)
        return _deterministic_prose(heading, items)


# ── send + persist (T073) ─────────────────────────────────────────────────────

_HEADING_TODAY = "ما حدث اليوم"
_HEADING_TOMORROW = "مهام الغد"


async def generate_and_send_daily_reports(
    conn: asyncpg.Connection,
    *,
    now: datetime | None = None,
    send: Sender | None = None,
) -> dict[str, int]:
    """Assemble → phrase → send to managers → write reports_log (one row/section).

    Runs in the worker's service (BYPASSRLS) context. ``send`` is injectable for
    tests; when None the WAHA sender is used. Managers without a phone are still
    logged (report row written, sent_at left null).
    """
    if send is None:
        from app.scheduler.waha import send_text

        send = send_text

    report = await assemble_daily_report(conn, now=now)

    firm = await conn.fetchrow(
        "SELECT waha_url, waha_key, llm_api_key, embedding_config FROM firm_settings LIMIT 1"
    )
    api_key = firm["llm_api_key"] if firm else None
    model = _model_from_firm(firm)

    today_prose = await phrase_section(
        _HEADING_TODAY, report.what_happened, api_key=api_key, model=model
    )
    tomorrow_prose = await phrase_section(
        _HEADING_TOMORROW, report.tomorrow, api_key=api_key, model=model
    )

    managers = await conn.fetch(
        "SELECT id, phone, status FROM users "
        "WHERE role = 'partner_manager' AND status = 'active'"
    )

    from app.scheduler.waha import WahaError

    session = _waha_session()
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    sections = (
        ("daily_what_happened", today_prose, report.what_happened),
        ("tomorrow_tasks", tomorrow_prose, report.tomorrow),
    )

    for report_type, prose, items in sections:
        items_json = [it.as_dict() for it in items]
        for m in managers:
            sent_at = None
            if firm and firm["waha_url"] and m["phone"]:
                try:
                    await send(
                        waha_url=firm["waha_url"],
                        waha_key=firm["waha_key"],
                        phone=m["phone"],
                        text=prose,
                        session=session,
                    )
                    sent_at = datetime.now(tz=FIRM_TZ)
                    counts["sent"] += 1
                except WahaError as exc:
                    logger.warning("reports: WAHA send failed for %s: %s", m["id"], exc)
                    counts["failed"] += 1
            else:
                counts["skipped"] += 1
            await _write_report_log(
                conn,
                report_type=report_type,
                recipient_user_id=m["id"],
                content=prose,
                items=items_json,
                sent_at=sent_at,
            )

    logger.info("reports: daily pass complete %s", counts)
    return counts


async def _write_report_log(
    conn: asyncpg.Connection,
    *,
    report_type: str,
    recipient_user_id: UUID,
    content: str,
    items: list[dict[str, Any]],
    sent_at: datetime | None,
) -> None:
    import json

    await conn.execute(
        """
        INSERT INTO reports_log (type, recipient_user_id, content, items, sent_at)
        VALUES ($1, $2, $3, $4, $5)
        """,
        report_type,
        recipient_user_id,
        content,
        json.dumps(items, ensure_ascii=False),
        sent_at,
    )


def _model_from_firm(firm: Any) -> str:
    cfg = firm["embedding_config"] if firm else None
    if isinstance(cfg, str):
        import json

        try:
            cfg = json.loads(cfg)
        except ValueError:
            cfg = None
    return (cfg or {}).get("llm_model", "models/gemini-2.0-flash")


def _waha_session() -> str:
    from app.core.config import get_settings

    return get_settings().waha_session
