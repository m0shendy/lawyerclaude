"""Hearing reminder scheduler — extends the deadline reminder pattern. [C-IV]

Runs as part of the daily scheduler pass (08:00 Africa/Cairo).
Sends WhatsApp reminders to assigned lawyers for upcoming hearings at the
same lead points configured in firm_settings (7d / 3d / 1d / 0d).

This is deterministic — no LLM involvement. [C-IV]
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import asyncpg

from app.scheduler.waha import WahaError, send_text

logger = logging.getLogger(__name__)

FIRM_TZ = ZoneInfo("Africa/Cairo")

# Lead-point field names in the hearings table
_LEAD_FIELDS = {
    7: "reminder_sent_7d",
    3: "reminder_sent_3d",
    1: "reminder_sent_1d",
    0: "reminder_sent_0d",
}


async def run_hearing_reminders(
    conn: asyncpg.Connection,
    *,
    waha_url: str,
    waha_key: str,
    sender=send_text,
) -> None:
    """Send hearing reminders for today's lead-point matches.

    Called by the daily scheduler worker — same connection pattern as reminders.py.
    Idempotent: skips hearings already marked with reminder_sent_Xd = true.
    """
    today = date.today()

    # Load configured lead points from firm_settings
    lead_raw = await conn.fetchval(
        "SELECT reminder_lead_points FROM firm_settings LIMIT 1"
    )
    import json
    lead_points_config: list[str] = json.loads(lead_raw) if lead_raw else ["7d", "3d", "1d", "0d"]
    lead_days_set = set()
    for lp in lead_points_config:
        if lp.endswith("d"):
            try:
                lead_days_set.add(int(lp[:-1]))
            except ValueError:
                pass

    for lead_days in sorted(lead_days_set, reverse=True):
        if lead_days not in _LEAD_FIELDS:
            continue
        field = _LEAD_FIELDS[lead_days]
        target_date = today + timedelta(days=lead_days)

        hearings = await conn.fetch(
            f"""
            SELECT h.id, h.hearing_date, h.court_name, h.court_room,
                   c.case_number, c.title AS case_title,
                   u.id AS lawyer_id, u.full_name, u.phone
            FROM hearings h
            JOIN cases c   ON h.case_id = c.id
            JOIN users u   ON h.assigned_lawyer_id = u.id
            WHERE h.hearing_date::date = $1
              AND h.status = 'scheduled'
              AND h.{field} = false
              AND u.status = 'active'
              AND u.phone IS NOT NULL
            """,
            target_date,
        )

        for h in hearings:
            message = _format_message(h, lead_days)
            lead_label = f"{lead_days}d"
            status = "sent"
            error_detail = None
            try:
                await sender(
                    waha_url=waha_url,
                    waha_key=waha_key,
                    phone=h["phone"],
                    text=message,
                )
            except WahaError as exc:
                logger.warning("WAHA error sending hearing reminder %s: %s", h["id"], exc)
                status = "failed"
                error_detail = str(exc)

            # Mark the reminder field only on successful send
            if status == "sent":
                await conn.execute(
                    f"UPDATE hearings SET {field} = true WHERE id = $1", h["id"]
                )

            # Log to notifications_log using hearing_id column (migration 0020)
            await conn.execute(
                """
                INSERT INTO notifications_log
                  (hearing_id, recipient_user_id, channel, lead_point,
                   scheduled_for, sent_at, status, error_detail)
                VALUES ($1, $2, 'whatsapp', $3, now(),
                        CASE WHEN $4 = 'sent' THEN now() ELSE NULL END,
                        $4::notification_status, $5)
                """,
                h["id"],
                h["lawyer_id"],
                lead_label,
                status,
                error_detail,
            )
            logger.info(
                "Hearing reminder (lead=%sd, hearing=%s, lawyer_phone=%s): %s",
                lead_days, h["id"], h["phone"], status,
            )


def _format_message(h: asyncpg.Record, lead_days: int) -> str:
    hearing_date_str = h["hearing_date"].strftime("%Y-%m-%d الساعة %H:%M")
    case_ref = h["case_number"] or h["case_title"]
    room = f" - {h['court_room']}" if h["court_room"] else ""

    if lead_days == 0:
        prefix = "🔔 تذكير اليوم"
    elif lead_days == 1:
        prefix = "⚠️ تذكير الغد"
    else:
        prefix = f"📅 تذكير ({lead_days} أيام)"

    return (
        f"{prefix}: جلسة قضية {case_ref}\n"
        f"المحكمة: {h['court_name']}{room}\n"
        f"الموعد: {hearing_date_str}"
    )
