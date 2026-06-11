"""Deterministic reminder + escalation logic — Component C (T067, T068). [C-IV]

This is the **Scheduler**: pure, deterministic code that decides *when* a
reminder fires and *who* receives it.  No LLM, no agent, ever touches this path
[C-IV].  The WhatsApp transport (``waha.send_text``) only carries the message.

What it does, on each daily pass (``run_reminders``):

  1. Read the firm's configurable lead points from
     ``firm_settings.reminder_lead_points`` (default 7d / 3d / 1d / same-day, R9).
  2. For every **confirmed** deadline (appeal types require ``confirmed=true``
     [C-X]; general deadlines are confirmed on creation), if today equals
     ``due_date - lead`` for any lead point, send the responsible lawyer a
     reminder.
  3. If a near-due deadline is **unacknowledged** (``acknowledged_at IS NULL``),
     additionally escalate to every active partner_manager.
  4. For every open/in-progress task with a due date, remind the assignee at the
     same lead points.
  5. Write a ``notifications_log`` row for **every** attempt — including
     ``failed`` (send error) and ``skipped`` (no phone / inactive recipient).
     A reminder is never silently dropped (FR-025). [C-IV]

Idempotency: a (item, recipient, lead_point, is_escalation) tuple already logged
as ``sent`` or ``skipped`` is not re-attempted.  ``failed`` rows are retried on
the next pass (transient WAHA/network errors should recover).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg

from app.scheduler.waha import WahaError, send_text

logger = logging.getLogger(__name__)

# Firm-local day boundary (Egypt). Lead-point matching is by calendar date in
# this timezone so "same-day" means the firm's today, not UTC's.
FIRM_TZ = ZoneInfo("Africa/Cairo")

# Escalate to a partner only inside this window before the due date, and only
# while the deadline is unacknowledged.
ESCALATION_MAX_DAYS = 1

# Default lead points if firm_settings has none (mirrors the 0002 DB default).
_DEFAULT_LEAD_POINTS = ["7d", "3d", "1d", "0d"]

# Type of the injectable sender — lets tests substitute a fake. Signature mirrors
# waha.send_text's keyword-only contract.
Sender = Callable[..., Awaitable[None]]


# ── lead points ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LeadPoint:
    label: str  # as configured, e.g. "3d" / "0d"
    days: int   # days before due_date this lead fires


def parse_lead_points(raw: Any) -> list[LeadPoint]:
    """Parse ``firm_settings.reminder_lead_points`` into sorted LeadPoints.

    Accepts a list (asyncpg may hand back a JSON string for a jsonb column, so a
    str is decoded first).  Each entry is ``"<n>d"`` (``"0d"`` = same day).
    Unparseable entries are skipped.  Result is de-duplicated and sorted
    descending by days (earliest reminder first).
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = None
    if not isinstance(raw, (list, tuple)) or not raw:
        raw = _DEFAULT_LEAD_POINTS

    seen: dict[int, LeadPoint] = {}
    for entry in raw:
        label = str(entry).strip().lower()
        digits = label.rstrip("d").strip()
        try:
            days = int(digits)
        except ValueError:
            logger.warning("reminders: skipping unparseable lead point %r", entry)
            continue
        if days < 0:
            continue
        seen.setdefault(days, LeadPoint(label=label, days=days))
    if not seen:
        return [LeadPoint(label=lp, days=int(lp.rstrip("d"))) for lp in _DEFAULT_LEAD_POINTS]
    return [seen[d] for d in sorted(seen, reverse=True)]


def matched_lead_point(
    due: date, today: date, lead_points: list[LeadPoint]
) -> LeadPoint | None:
    """Return the lead point firing today for *due*, or None.

    A lead point fires when ``today == due - days``.  If several match (unusual),
    the most urgent (fewest days) wins.
    """
    days_until = (due - today).days
    candidates = [lp for lp in lead_points if lp.days == days_until]
    if not candidates:
        return None
    return min(candidates, key=lambda lp: lp.days)


def should_escalate(due: date, today: date, acknowledged: bool) -> bool:
    """Escalate when an unacknowledged deadline is within the escalation window."""
    if acknowledged:
        return False
    days_until = (due - today).days
    return 0 <= days_until <= ESCALATION_MAX_DAYS


# ── message builders (deterministic; the LLM does not phrase reminders) ───────


def _due_phrase(due: date, today: date) -> str:
    days_until = (due - today).days
    if days_until <= 0:
        return f"المستحق اليوم ({due.isoformat()})"
    if days_until == 1:
        return f"المستحق غدًا ({due.isoformat()})"
    return f"المستحق خلال {days_until} يوم ({due.isoformat()})"


def build_deadline_message(title: str, case_title: str, due: date, today: date) -> str:
    return (
        f"تذكير بموعد: «{title}» في القضية «{case_title}» {_due_phrase(due, today)}. "
        f"يُرجى المتابعة والإقرار بالاستلام."
    )


def build_escalation_message(
    title: str, case_title: str, due: date, today: date, lawyer_name: str
) -> str:
    return (
        f"تصعيد: لم يُقِرّ المحامي المسؤول ({lawyer_name}) باستلام تذكير الموعد "
        f"«{title}» في القضية «{case_title}» {_due_phrase(due, today)}. يُرجى المتابعة."
    )


def build_task_message(description: str, case_title: str, due: date, today: date) -> str:
    return (
        f"تذكير بمهمة: «{description}» في القضية «{case_title}» {_due_phrase(due, today)}."
    )


# ── persistence helpers ───────────────────────────────────────────────────────


async def _already_handled(
    conn: asyncpg.Connection,
    *,
    deadline_id: UUID | None,
    task_id: UUID | None,
    recipient_user_id: UUID,
    lead_point: str,
    is_escalation: bool,
) -> bool:
    """True if this exact reminder was already sent or deliberately skipped.

    ``failed`` rows are NOT considered handled, so transient failures retry.
    """
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM notifications_log
                WHERE deadline_id IS NOT DISTINCT FROM $1
                  AND task_id     IS NOT DISTINCT FROM $2
                  AND recipient_user_id = $3
                  AND lead_point = $4
                  AND is_escalation = $5
                  AND status IN ('sent', 'skipped')
            )
            """,
            deadline_id,
            task_id,
            recipient_user_id,
            lead_point,
            is_escalation,
        )
    )


async def _log_attempt(
    conn: asyncpg.Connection,
    *,
    deadline_id: UUID | None,
    task_id: UUID | None,
    recipient_user_id: UUID,
    lead_point: str,
    is_escalation: bool,
    scheduled_for: datetime,
    status: str,
    sent_at: datetime | None,
    error_detail: str | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO notifications_log
            (deadline_id, task_id, recipient_user_id, channel, lead_point,
             is_escalation, scheduled_for, sent_at, status, error_detail)
        VALUES ($1, $2, $3, 'whatsapp', $4, $5, $6, $7, $8, $9)
        """,
        deadline_id,
        task_id,
        recipient_user_id,
        lead_point,
        is_escalation,
        scheduled_for,
        sent_at,
        status,
        error_detail,
    )


@dataclass
class RunSummary:
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    duplicate: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "sent": self.sent,
            "failed": self.failed,
            "skipped": self.skipped,
            "duplicate": self.duplicate,
        }


async def _dispatch(
    conn: asyncpg.Connection,
    summary: RunSummary,
    *,
    deadline_id: UUID | None,
    task_id: UUID | None,
    recipient_user_id: UUID,
    recipient_phone: str | None,
    recipient_status: str,
    lead_point: str,
    is_escalation: bool,
    scheduled_for: datetime,
    text: str,
    waha_url: str | None,
    waha_key: str | None,
    session: str,
    send: Sender,
) -> None:
    """Send one reminder and record exactly one notifications_log row.

    Skips (without a new row) only when an identical attempt already succeeded
    or was skipped — otherwise always writes a row (sent / failed / skipped).
    """
    if await _already_handled(
        conn,
        deadline_id=deadline_id,
        task_id=task_id,
        recipient_user_id=recipient_user_id,
        lead_point=lead_point,
        is_escalation=is_escalation,
    ):
        summary.duplicate += 1
        return

    # Recipient must be reachable: active + has a verified phone. Otherwise the
    # attempt is recorded as 'skipped' (never silently dropped). FR-025
    if recipient_status != "active" or not recipient_phone:
        reason = (
            "المستلم غير نشط"
            if recipient_status != "active"
            else "لا يوجد رقم هاتف مُوثّق للمستلم"
        )
        await _log_attempt(
            conn,
            deadline_id=deadline_id,
            task_id=task_id,
            recipient_user_id=recipient_user_id,
            lead_point=lead_point,
            is_escalation=is_escalation,
            scheduled_for=scheduled_for,
            status="skipped",
            sent_at=None,
            error_detail=reason,
        )
        summary.skipped += 1
        return

    try:
        await send(
            waha_url=waha_url,
            waha_key=waha_key,
            phone=recipient_phone,
            text=text,
            session=session,
        )
    except WahaError as exc:
        await _log_attempt(
            conn,
            deadline_id=deadline_id,
            task_id=task_id,
            recipient_user_id=recipient_user_id,
            lead_point=lead_point,
            is_escalation=is_escalation,
            scheduled_for=scheduled_for,
            status="failed",
            sent_at=None,
            error_detail=str(exc)[:500],
        )
        summary.failed += 1
        return

    await _log_attempt(
        conn,
        deadline_id=deadline_id,
        task_id=task_id,
        recipient_user_id=recipient_user_id,
        lead_point=lead_point,
        is_escalation=is_escalation,
        scheduled_for=scheduled_for,
        status="sent",
        sent_at=datetime.now(timezone.utc),
        error_detail=None,
    )
    summary.sent += 1


# ── orchestration ─────────────────────────────────────────────────────────────


async def run_all_reminders(
    conn: asyncpg.Connection,
    *,
    now: datetime | None = None,
    send: Sender = send_text,
) -> RunSummary:
    """Multi-tenant orchestrator: one deterministic pass PER eligible firm.

    Suspended/cancelled firms are skipped entirely (no reminders). Failures in
    one firm's pass never block the next firm. [C-I v2][C-IV]
    """
    from app.core.tenancy import active_firm_ids

    total = RunSummary()
    for firm_id in await active_firm_ids(conn):
        try:
            s = await run_reminders(conn, firm_id=firm_id, now=now, send=send)
            total.sent += s.sent
            total.failed += s.failed
            total.skipped += s.skipped
        except Exception:
            logger.exception("reminders: firm %s pass failed — continuing", firm_id)
    return total


async def run_reminders(
    conn: asyncpg.Connection,
    *,
    firm_id: UUID,
    now: datetime | None = None,
    send: Sender = send_text,
) -> RunSummary:
    """Run one deterministic reminder pass for ONE firm. Returns counts.

    The DB connection must come from a system context (worker, BYPASSRLS) so the
    scheduler sees every firm row; tenant scope is the explicit ``firm_id``
    filter on every query below. ``send`` is injectable for tests. [C-I v2]
    """
    now = now or datetime.now(tz=FIRM_TZ)
    today = now.astimezone(FIRM_TZ).date()
    summary = RunSummary()

    settings_row = await conn.fetchrow(
        "SELECT waha_url, waha_key, reminder_lead_points "
        "FROM firm_settings WHERE firm_id = $1",
        firm_id,
    )
    if settings_row is None:
        logger.warning("reminders: no firm_settings row — nothing to do")
        return summary

    waha_url = settings_row["waha_url"]
    waha_key = settings_row["waha_key"]
    session = _waha_session()
    lead_points = parse_lead_points(settings_row["reminder_lead_points"])
    lead_labels = {lp.days: lp.label for lp in lead_points}

    # Active partner_managers receive escalations.
    partner_rows = await conn.fetch(
        "SELECT id, full_name, phone, status FROM users "
        "WHERE role = 'partner_manager' AND status = 'active' AND firm_id = $1",
        firm_id,
    )

    # ── confirmed deadlines ──────────────────────────────────────────────────
    deadlines = await conn.fetch(
        """
        SELECT d.id, d.title, d.due_date, d.acknowledged_at,
               d.responsible_user_id, c.title AS case_title,
               u.full_name AS responsible_name, u.phone AS responsible_phone,
               u.status AS responsible_status
        FROM deadlines d
        JOIN cases c ON c.id = d.case_id
        JOIN users u ON u.id = d.responsible_user_id
        WHERE d.confirmed = true AND d.firm_id = $1
        """,
        firm_id,
    )
    for d in deadlines:
        due: date = d["due_date"]
        lp = matched_lead_point(due, today, lead_points)
        if lp is not None:
            await _dispatch(
                conn,
                summary,
                deadline_id=d["id"],
                task_id=None,
                recipient_user_id=d["responsible_user_id"],
                recipient_phone=d["responsible_phone"],
                recipient_status=d["responsible_status"],
                lead_point=lp.label,
                is_escalation=False,
                scheduled_for=now,
                text=build_deadline_message(d["title"], d["case_title"], due, today),
                waha_url=waha_url,
                waha_key=waha_key,
                session=session,
                send=send,
            )

        # Escalation to partners — unacknowledged + within window. Tag the row
        # with the firing lead label (or the most-urgent configured one) so the
        # idempotency key is stable across the day.
        if should_escalate(due, today, d["acknowledged_at"] is not None):
            days_until = (due - today).days
            esc_label = lead_labels.get(days_until, f"{days_until}d")
            for p in partner_rows:
                if p["id"] == d["responsible_user_id"]:
                    continue  # responsible lawyer is the partner — already reminded
                await _dispatch(
                    conn,
                    summary,
                    deadline_id=d["id"],
                    task_id=None,
                    recipient_user_id=p["id"],
                    recipient_phone=p["phone"],
                    recipient_status=p["status"],
                    lead_point=esc_label,
                    is_escalation=True,
                    scheduled_for=now,
                    text=build_escalation_message(
                        d["title"], d["case_title"], due, today, d["responsible_name"]
                    ),
                    waha_url=waha_url,
                    waha_key=waha_key,
                    session=session,
                    send=send,
                )

    # ── open tasks with due dates ────────────────────────────────────────────
    tasks = await conn.fetch(
        """
        SELECT t.id, t.description, t.due_date, t.assigned_to,
               c.title AS case_title,
               u.phone AS assignee_phone, u.status AS assignee_status
        FROM tasks t
        JOIN cases c ON c.id = t.case_id
        JOIN users u ON u.id = t.assigned_to
        WHERE t.status IN ('open', 'in_progress') AND t.due_date IS NOT NULL
              AND t.firm_id = $1
        """,
        firm_id,
    )
    for t in tasks:
        due = t["due_date"]
        lp = matched_lead_point(due, today, lead_points)
        if lp is None:
            continue
        await _dispatch(
            conn,
            summary,
            deadline_id=None,
            task_id=t["id"],
            recipient_user_id=t["assigned_to"],
            recipient_phone=t["assignee_phone"],
            recipient_status=t["assignee_status"],
            lead_point=lp.label,
            is_escalation=False,
            scheduled_for=now,
            text=build_task_message(t["description"], t["case_title"], due, today),
            waha_url=waha_url,
            waha_key=waha_key,
            session=session,
            send=send,
        )

    logger.info("reminders: pass complete %s", summary.as_dict())
    return summary


def _waha_session() -> str:
    # Imported lazily so importing this module doesn't require settings at import
    # time (keeps the pure logic unit-testable without env).
    from app.core.config import get_settings

    return get_settings().waha_session
