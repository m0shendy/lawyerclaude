"""Authentication (T020).

Verifies the Supabase GoTrue JWT from `Authorization: Bearer` and resolves
the `users` row (profile + role). Supports both signing schemes:

* **HS256** — legacy shared secret (`GOTRUE_JWT_SECRET`), used by self-hosted
  GoTrue stacks and by tests that mint their own tokens.
* **ES256/RS256** — asymmetric signing keys used by Supabase Cloud projects;
  the public key is fetched (and cached) from the project's JWKS endpoint
  (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`).

Only `active` users authenticate — inactive users are rejected everywhere,
including the assistant channel (R12). Tenant isolation is enforced via the
`firm_id` carried on the resolved user row. [C-I]
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError
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


@lru_cache
def _jwks_client() -> PyJWKClient:
    """JWKS client for asymmetric (Supabase Cloud) token verification, cached."""
    settings = get_settings()
    return PyJWKClient(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
        cache_keys=True,
        lifespan=3600,
    )


def _decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise ApiError(401, "invalid_token", "جلسة غير صالحة — يرجى تسجيل الدخول") from exc

    try:
        if header.get("alg") == "HS256":
            # Legacy shared-secret signing (self-hosted GoTrue, tests).
            if not settings.gotrue_jwt_secret:
                raise ApiError(500, "misconfigured", "GOTRUE_JWT_SECRET is not configured")
            return jwt.decode(
                token,
                settings.gotrue_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        # Asymmetric signing (Supabase Cloud) — verify against the project JWKS.
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except (jwt.InvalidTokenError, PyJWKClientError) as exc:
        raise ApiError(401, "invalid_token", "جلسة غير صالحة — يرجى تسجيل الدخول") from exc


async def load_user_by_auth_id(auth_user_id: str) -> CurrentUser:
    """Fetch the profile row for a GoTrue subject; reject missing/inactive/suspended."""
    # Imported lazily to avoid a circular import: db.py depends on get_current_user.
    from app.core.db import db_connection

    async with db_connection(None, "auth:resolve") as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.auth_user_id, u.firm_id, u.full_name, u.email, u.phone,
                   u.role::text AS role, u.status::text AS status,
                   f.status::text AS firm_status
            FROM users u
            JOIN firms f ON f.id = u.firm_id
            WHERE u.auth_user_id = $1
            """,
            UUID(auth_user_id),
        )
    if row is None:
        raise ApiError(401, "unknown_user", "المستخدم غير مسجل في هذه المنشأة")
    if row["status"] != "active":
        raise ApiError(401, "inactive_user", "تم إيقاف هذا الحساب — تواصل مع مدير المكتب")
    # Suspended/cancelled firms: block all API access immediately (T020). [C-I]
    if row["firm_status"] in ("suspended", "cancelled"):
        raise ApiError(403, "firm_suspended", "تم إيقاف تشغيل المكتب — تواصل مع مشغّل المنصة")
    data = {k: v for k, v in dict(row).items() if k != "firm_status"}
    return CurrentUser(**data)


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
