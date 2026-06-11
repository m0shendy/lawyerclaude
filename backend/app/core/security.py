"""Authentication (T020).

Verifies the Supabase GoTrue JWT (HS256) from `Authorization: Bearer` and
resolves the per-instance `users` row (profile + role). Only `active` users
authenticate — inactive users are rejected everywhere, including the
assistant channel (R12). Per-firm isolation is the instance boundary: this
backend only ever sees its own firm's GoTrue + users table. [C-I]
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import ApiError

Role = Literal["partner_manager", "lawyer", "paralegal", "secretary"]

_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: UUID
    auth_user_id: UUID
    firm_id: UUID
    full_name: str
    email: str
    phone: str | None
    role: Role
    status: str


def _decode_token(token: str) -> dict:
    settings = get_settings()
    if not settings.gotrue_jwt_secret:
        raise ApiError(500, "misconfigured", "GOTRUE_JWT_SECRET is not configured")
    try:
        return jwt.decode(
            token,
            settings.gotrue_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.InvalidTokenError as exc:
        raise ApiError(401, "invalid_token", "جلسة غير صالحة — يرجى تسجيل الدخول") from exc


async def load_user_by_auth_id(auth_user_id: str) -> CurrentUser:
    """Fetch the profile row for a GoTrue subject; reject missing/inactive."""
    # Imported lazily to avoid a circular import: db.py depends on get_current_user.
    from app.core.db import db_connection

    async with db_connection(None, "auth:resolve") as conn:
        row = await conn.fetchrow(
            """
            SELECT id, auth_user_id, firm_id, full_name, email, phone, role::text AS role, status::text AS status
            FROM users
            WHERE auth_user_id = $1
            """,
            UUID(auth_user_id),
        )
    if row is None:
        raise ApiError(401, "unknown_user", "المستخدم غير مسجل في هذه المنشأة")
    if row["status"] != "active":
        raise ApiError(401, "inactive_user", "تم إيقاف هذا الحساب — تواصل مع مدير المكتب")
    return CurrentUser(**dict(row))


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None:
        raise ApiError(401, "unauthenticated", "مطلوب تسجيل الدخول")
    claims = _decode_token(credentials.credentials)
    sub = claims.get("sub")
    if not sub:
        raise ApiError(401, "invalid_token", "جلسة غير صالحة")
    user = await load_user_by_auth_id(sub)
    # Expose to get_db so the request's DB connection carries the audit GUCs.
    request.state.current_user = user
    return user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
