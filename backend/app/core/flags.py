"""Per-instance feature flags (T022, T076). [C-X]

Flags live on the singleton `firm_settings` row. `feature_appeal_deadlines`
defaults FALSE and stays off until an expert lawyer blesses the appeal
calculation logic — the suggestion generator and UI are both gated on it.
"""

from __future__ import annotations

import asyncpg

from app.core.errors import ApiError

_KNOWN_FLAGS = {"feature_appeal_deadlines"}


async def get_flag(conn: asyncpg.Connection, name: str) -> bool:
    if name not in _KNOWN_FLAGS:
        raise ValueError(f"unknown feature flag: {name}")
    value = await conn.fetchval(f"SELECT {name} FROM firm_settings LIMIT 1")  # noqa: S608 — name validated above
    return bool(value)


async def require_flag(conn: asyncpg.Connection, name: str) -> None:
    """403 if the flag is off — the feature is invisible/inert. [C-X]"""
    if not await get_flag(conn, name):
        raise ApiError(403, "feature_disabled", "هذه الخاصية غير مفعّلة لهذه المنشأة")
