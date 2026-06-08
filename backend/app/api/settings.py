"""Firm settings endpoints (manager only). [C-III][C-XI]

GET  /settings   — returns the firm_settings row with secret fields MASKED.
PATCH /settings  — updates any editable field; secret changes are logged by
                   the DB audit trigger as "[REDACTED]", never as the value.

Secret fields (waha_key, llm_api_key):
- GET:  returned as None when not set, or the sentinel "••••••••" when set.
        The actual value is NEVER returned to the API client.
- PATCH: if the client sends the sentinel "••••••••" we leave the stored value
         unchanged (avoids overwriting a secret with its masked placeholder).
         Empty string "" clears the field.

[C-III] The DB audit trigger (0005) already redacts these columns field-level.
[C-XI]  WAHA URL/key and LLM key are per-instance; only the manager may set them.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import MANAGER, require_roles
from app.core.security import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()

ManagerDep = Depends(require_roles(MANAGER))

_SECRET_SENTINEL = "••••••••"
_SECRET_COLS = {"waha_key", "llm_api_key"}

_ALL_COLS = (
    "id, firm_name, locale, waha_url, waha_key, llm_api_key, "
    "llm_provider_config, checkout_timeout_hours, "
    "embedding_config, reminder_lead_points, feature_appeal_deadlines, "
    "feature_client_portal, subscription_metadata, created_at, updated_at"
)


class SettingsOut(BaseModel):
    id: str
    firm_name: str
    locale: str
    waha_url: str | None
    waha_key_set: bool
    llm_api_key_set: bool
    llm_provider_config: dict[str, Any]
    checkout_timeout_hours: int
    embedding_config: dict[str, Any]
    reminder_lead_points: list[str]
    feature_appeal_deadlines: bool
    feature_client_portal: bool
    subscription_metadata: dict[str, Any]
    created_at: str
    updated_at: str


class SettingsUpdate(BaseModel):
    firm_name: str | None = None
    locale: str | None = None
    waha_url: str | None = None
    waha_key: str | None = None         # set to "" to clear; "••••" = leave unchanged
    llm_api_key: str | None = None      # same sentinel behaviour
    llm_provider_config: dict[str, Any] | None = None  # {provider, model} — key stays in llm_api_key
    checkout_timeout_hours: int | None = None
    embedding_config: dict[str, Any] | None = None
    reminder_lead_points: list[str] | None = None
    feature_appeal_deadlines: bool | None = None
    feature_client_portal: bool | None = None


def _row_to_out(row) -> SettingsOut:
    d = dict(row)

    # jsonb columns may come back as a dict (asyncpg decodes jsonb) or string.
    def _ensure_dict(v: Any) -> dict:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or {}

    def _ensure_list(v: Any) -> list:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return list(v) if v else []

    return SettingsOut(
        id=str(d["id"]),
        firm_name=d["firm_name"] or "",
        locale=d["locale"] or "ar-EG",
        waha_url=d.get("waha_url"),
        waha_key_set=bool(d.get("waha_key")),
        llm_api_key_set=bool(d.get("llm_api_key")),
        llm_provider_config=_ensure_dict(d.get("llm_provider_config")),
        checkout_timeout_hours=int(d.get("checkout_timeout_hours") or 24),
        embedding_config=_ensure_dict(d.get("embedding_config")),
        reminder_lead_points=_ensure_list(d.get("reminder_lead_points")),
        feature_appeal_deadlines=bool(d.get("feature_appeal_deadlines")),
        feature_client_portal=bool(d.get("feature_client_portal")),
        subscription_metadata=_ensure_dict(d.get("subscription_metadata")),
        created_at=str(d["created_at"]),
        updated_at=str(d["updated_at"]),
    )


@router.get("/settings", response_model=SettingsOut)
async def get_settings(
    conn: Db,
    _manager: Annotated[CurrentUser, ManagerDep],
) -> SettingsOut:
    row = await conn.fetchrow(f"SELECT {_ALL_COLS} FROM firm_settings LIMIT 1")
    if row is None:
        raise ApiError(404, "not_found", "إعدادات المكتب غير مُهيَّأة")
    return _row_to_out(row)


@router.patch("/settings", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate,
    conn: Db,
    _manager: Annotated[CurrentUser, ManagerDep],
) -> SettingsOut:
    updates = body.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        row = await conn.fetchrow(f"SELECT {_ALL_COLS} FROM firm_settings LIMIT 1")
        if row is None:
            raise ApiError(404, "not_found", "إعدادات المكتب غير مُهيَّأة")
        return _row_to_out(row)

    # Secret sentinel: if the client echoes "••••••••" for a secret field,
    # treat as "leave unchanged" (client is sending back the masked placeholder).
    for col in _SECRET_COLS:
        if col in updates and updates[col] == _SECRET_SENTINEL:
            del updates[col]

    # Serialize jsonb fields to JSON string for asyncpg.
    if "llm_provider_config" in updates:
        cfg = updates["llm_provider_config"]
        # Defence in depth: never accept a key inside the config blob —
        # the secret lives only in llm_api_key (audit-redacted) [C-III].
        cfg.pop("api_key", None)
        updates["llm_provider_config"] = json.dumps(cfg)
    if "embedding_config" in updates:
        updates["embedding_config"] = json.dumps(updates["embedding_config"])
    if "reminder_lead_points" in updates:
        updates["reminder_lead_points"] = json.dumps(updates["reminder_lead_points"])

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")

    row = await conn.fetchrow(
        f"""
        UPDATE firm_settings
        SET {", ".join(parts)}, updated_at = now()
        WHERE singleton = true
        RETURNING {_ALL_COLS}
        """,
        *params,
    )
    if row is None:
        raise ApiError(404, "not_found", "إعدادات المكتب غير مُهيَّأة")

    logger.info(
        "firm_settings updated: fields=%s (secrets masked)",
        [k for k in updates if k not in _SECRET_COLS]
    )
    return _row_to_out(row)


# ── LLM provider test connection (spec 002 FR-141) ────────────────────────────


class LlmTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_ms: int


@router.post("/settings/llm-provider/test", response_model=LlmTestResponse)
async def test_llm_provider(
    conn: Db,
    _manager: Annotated[CurrentUser, ManagerDep],
) -> LlmTestResponse:
    """Dispatch a tiny test prompt via the configured provider; report latency.

    The key is read server-side from firm_settings and never echoed. [C-III]
    """
    import time

    from app.llm.generate import LlmError
    from app.llm.providers import dispatch, load_llm_context

    api_key, cfg = await load_llm_context(conn)
    started = time.monotonic()
    try:
        await dispatch(
            "أجب بكلمة واحدة فقط: جاهز",
            api_key=api_key,
            provider_config=cfg,
            max_output_tokens=16,
            timeout=30.0,
        )
    except LlmError as exc:
        raise ApiError(502, "llm_test_failed", str(exc)) from exc
    latency_ms = int((time.monotonic() - started) * 1000)
    return LlmTestResponse(
        ok=True,
        provider=str(cfg.get("provider", "")),
        model=str(cfg.get("model", "")),
        latency_ms=latency_ms,
    )
