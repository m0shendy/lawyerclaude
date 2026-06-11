"""User management endpoints (T031): manager-only CRUD per rest-api.md.

GoTrue owns credentials; the `users` table holds profile + role [C-I]. Creation
provisions the GoTrue user first, then the profile row (with best-effort GoTrue
cleanup if the profile insert fails). Deactivation is the preferred removal path:
it blocks login + assistant (security.py rejects inactive users) and we also ban
the GoTrue account best-effort. Hard delete is refused (409) while the user still
has case assignments, owned tasks, or responsible deadlines. All mutations flow
through the audited Db connection — the DB triggers write the audit rows [C-III].
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import MANAGER, require_roles
from app.core.security import CurrentUser
from app.models import User, UserCreate, UserUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

ManagerDep = Depends(require_roles(MANAGER))

_USER_COLUMNS = "id, auth_user_id, full_name, email, phone, role, status, created_at"


def _admin_headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "apikey": settings.supabase_service_key,
        "authorization": f"Bearer {settings.supabase_service_key}",
    }


async def _gotrue_set_ban(auth_user_id: UUID | None, *, ban: bool) -> None:
    """Best-effort GoTrue ban/unban on (de)activation; failure is logged, not raised."""
    if auth_user_id is None:
        return
    settings = get_settings()
    duration = "876000h" if ban else "none"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.put(
                f"{settings.supabase_url}/auth/v1/admin/users/{auth_user_id}",
                headers=_admin_headers(),
                json={"ban_duration": duration},
            )
        if resp.status_code >= 400:
            logger.warning(
                "GoTrue ban update failed (auth_user_id=%s, ban=%s, status=%s)",
                auth_user_id,
                ban,
                resp.status_code,
            )
    except httpx.HTTPError:
        logger.warning(
            "GoTrue ban update unreachable (auth_user_id=%s, ban=%s)", auth_user_id, ban
        )


async def _gotrue_delete(auth_user_id: UUID | None) -> None:
    """Best-effort GoTrue admin delete; failure is logged, not raised."""
    if auth_user_id is None:
        return
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.delete(
                f"{settings.supabase_url}/auth/v1/admin/users/{auth_user_id}",
                headers=_admin_headers(),
            )
        if resp.status_code >= 400:
            logger.warning(
                "GoTrue delete failed (auth_user_id=%s, status=%s)",
                auth_user_id,
                resp.status_code,
            )
    except httpx.HTTPError:
        logger.warning("GoTrue delete unreachable (auth_user_id=%s)", auth_user_id)


async def _fetch_user_or_404(conn, user_id: UUID):
    row = await conn.fetchrow(f"SELECT {_USER_COLUMNS} FROM users WHERE id = $1", user_id)
    if row is None:
        raise ApiError(404, "not_found", "المستخدم غير موجود")
    return row


@router.get("/users", response_model=list[User])
async def list_users(
    conn: Db,
    _manager: CurrentUser = ManagerDep,
) -> list[User]:
    rows = await conn.fetch(f"SELECT {_USER_COLUMNS} FROM users ORDER BY created_at")
    return [User(**dict(r)) for r in rows]


@router.post("/users", response_model=User, status_code=201)
async def create_user(
    body: UserCreate,
    conn: Db,
    _manager: CurrentUser = ManagerDep,
) -> User:
    settings = get_settings()

    # 1) Provision the GoTrue credential first — it owns auth [C-I].
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.supabase_url}/auth/v1/admin/users",
                headers=_admin_headers(),
                json={
                    "email": body.email,
                    "password": body.password,
                    "email_confirm": True,
                },
            )
    except httpx.HTTPError as exc:
        raise ApiError(502, "auth_provider_error", "تعذر الاتصال بخدمة المصادقة") from exc
    if resp.status_code not in (200, 201):
        if resp.status_code in (409, 422):
            raise ApiError(409, "invalid_state", "البريد الإلكتروني مسجل بالفعل")
        logger.warning("GoTrue admin create failed (status=%s)", resp.status_code)
        raise ApiError(502, "auth_provider_error", "تعذر إنشاء حساب المصادقة")
    auth_user_id = resp.json().get("id")
    if not auth_user_id:
        raise ApiError(502, "auth_provider_error", "استجابة غير متوقعة من خدمة المصادقة")

    # 2) Insert the profile row (audited by DB trigger). On failure, best-effort
    #    cleanup of the GoTrue user so we don't strand an orphan credential.
    try:
        row = await conn.fetchrow(
            f"""
            INSERT INTO users (firm_id, auth_user_id, full_name, email, phone, role)
            VALUES ($6, $1, $2, $3, $4, $5)
            RETURNING {_USER_COLUMNS}
            """,
            UUID(auth_user_id),
            body.full_name,
            body.email,
            body.phone,
            body.role,
            _manager.firm_id,
        )
    except Exception:
        await _gotrue_delete(UUID(auth_user_id))
        raise
    return User(**dict(row))


@router.patch("/users/{user_id}", response_model=User)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    conn: Db,
    manager: CurrentUser = ManagerDep,
) -> User:
    existing = await _fetch_user_or_404(conn, user_id)

    # Self-protection: a manager cannot deactivate themselves, nor demote their
    # own role (sole-manager lockout would orphan user/audit administration).
    if body.status == "inactive" and user_id == manager.id:
        raise ApiError(409, "invalid_state", "لا يمكنك إلغاء تفعيل حسابك الخاص")
    if body.role is not None and body.role != MANAGER and user_id == manager.id:
        raise ApiError(409, "invalid_state", "لا يمكنك تغيير دور حسابك الخاص")

    updates = body.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return User(**dict(existing))

    set_parts = []
    params: list = []
    for field, value in updates.items():
        params.append(value)
        set_parts.append(f"{field} = ${len(params)}")
    params.append(user_id)
    row = await conn.fetchrow(
        f"""
        UPDATE users SET {", ".join(set_parts)}, updated_at = now()
        WHERE id = ${len(params)}
        RETURNING {_USER_COLUMNS}
        """,
        *params,
    )
    if row is None:  # raced delete between fetch and update
        raise ApiError(404, "not_found", "المستخدم غير موجود")

    # Mirror status changes into GoTrue (ban on deactivate, unban on reactivate);
    # best-effort — security.py rejects inactive profiles regardless.
    new_status = updates.get("status")
    if new_status is not None and new_status != existing["status"]:
        await _gotrue_set_ban(existing["auth_user_id"], ban=(new_status == "inactive"))

    return User(**dict(row))


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    conn: Db,
    manager: CurrentUser = ManagerDep,
) -> dict:
    if user_id == manager.id:
        raise ApiError(409, "invalid_state", "لا يمكنك حذف حسابك الخاص")

    existing = await _fetch_user_or_404(conn, user_id)

    # Prefer deactivation: refuse hard delete while the user is referenced.
    referenced = await conn.fetchval(
        """
        SELECT EXISTS (SELECT 1 FROM case_assignments WHERE user_id = $1)
            OR EXISTS (SELECT 1 FROM tasks WHERE assigned_to = $1)
            OR EXISTS (SELECT 1 FROM deadlines WHERE responsible_user_id = $1)
        """,
        user_id,
    )
    if referenced:
        raise ApiError(
            409,
            "invalid_state",
            "لا يمكن حذف المستخدم لارتباطه بقضايا أو مهام أو مواعيد — قم بإلغاء التفعيل بدلاً من ذلك",
        )

    await conn.execute("DELETE FROM users WHERE id = $1", user_id)
    await _gotrue_delete(existing["auth_user_id"])
    return {"status": "deleted"}
