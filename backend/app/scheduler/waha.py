"""WAHA (WhatsApp HTTP API) client — outbound only (T066).

The firm's **WAHA Plus session is the tenant identifier**; its endpoint and key
live in ``firm_settings`` (``waha_url``, ``waha_key`` — SECRETS, never logged as
values [C-III]).  This module is a thin, deterministic HTTP sender used by the
scheduler (Component C) for reminders and reports.  It NEVER decides whether or
to whom to send — that is the scheduler's deterministic logic [C-IV]; this only
performs the transport.

WAHA Plus REST contract (send text):
    POST {waha_url}/api/sendText
    headers: X-Api-Key: {waha_key}
    body:    {"session": "<name>", "chatId": "<digits>@c.us", "text": "<msg>"}

Phone → chatId: WAHA expects ``<international-digits>@c.us``.  We strip every
non-digit from the verified phone and append the suffix.
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_SEND_TEXT_PATH = "/api/sendText"
_CHAT_SUFFIX = "@c.us"


class WahaError(Exception):
    """Raised when an outbound WhatsApp send fails (config, network, API)."""


def phone_to_chat_id(phone: str) -> str:
    """Normalize a verified phone to a WAHA chatId (``<digits>@c.us``)."""
    digits = re.sub(r"\D", "", phone or "")
    return f"{digits}{_CHAT_SUFFIX}"


async def send_text(
    *,
    waha_url: str | None,
    waha_key: str | None,
    phone: str,
    text: str,
    session: str = "default",
    timeout: float = 30.0,
) -> None:
    """Send one WhatsApp text message to *phone* via the firm's WAHA session.

    Args:
        waha_url:  Firm WAHA endpoint (``firm_settings.waha_url``).
        waha_key:  Firm WAHA API key (``firm_settings.waha_key`` — SECRET).
        phone:     Recipient's verified phone (any format; normalized here).
        text:      Message body (built deterministically by the caller).
        session:   WAHA session name (per-firm tenant); default ``"default"``.
        timeout:   HTTP timeout in seconds.

    Raises:
        WahaError: On missing config, an unreachable endpoint, or a non-2xx
        response.  The caller (reminders.py) catches this and records a
        ``failed`` notifications_log row — a send is never silently dropped.
    """
    if not waha_url:
        raise WahaError("عنوان WAHA غير مضبوط في إعدادات المكتب")
    if not phone or not re.search(r"\d", phone):
        raise WahaError("رقم الهاتف غير صالح للمستلم")

    url = waha_url.rstrip("/") + _SEND_TEXT_PATH
    body = {"session": session, "chatId": phone_to_chat_id(phone), "text": text}
    headers: dict[str, str] = {}
    if waha_key:
        headers["X-Api-Key"] = waha_key

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:  # network / DNS / timeout
        raise WahaError(f"تعذّر الاتصال بخدمة واتساب: {exc}") from exc

    if resp.status_code >= 400:
        # Never include waha_key; resp.text is WAHA's own error body.
        raise WahaError(
            f"خدمة واتساب أعادت خطأ {resp.status_code}: {resp.text[:300]}"
        )

    logger.info("waha: sent text to %s (session=%s)", phone_to_chat_id(phone), session)
