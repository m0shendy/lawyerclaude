"""Auth endpoints (T025): /auth/login, /auth/logout, /me.

Login proxies to the per-instance GoTrue (password grant) — per-instance users
only [C-I]; a user from another firm's instance simply does not exist in this
GoTrue/users table. Inactive users are rejected even with valid credentials.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.db import Db
from app.core.errors import ApiError
from app.core.security import CurrentUserDep, load_user_by_auth_id
from app.models import Case, User

logger = logging.getLogger(__name__)

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: User


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": settings.supabase_service_key},
            json={"email": body.email, "password": body.password},
        )
    if resp.status_code != 200:
        # Never echo GoTrue internals; uniform message avoids account probing.
        raise ApiError(401, "invalid_credentials", "بيانات الدخول غير صحيحة")
    session = resp.json()
    auth_user_id = session.get("user", {}).get("id")
    if not auth_user_id:
        raise ApiError(401, "invalid_credentials", "بيانات الدخول غير صحيحة")

    # Resolve the profile row; rejects unknown AND inactive users.
    current = await load_user_by_auth_id(auth_user_id)

    return LoginResponse(
        access_token=session["access_token"],
        refresh_token=session.get("refresh_token", ""),
        expires_in=session.get("expires_in", 3600),
        user=User(
            id=current.id,
            auth_user_id=current.auth_user_id,
            full_name=current.full_name,
            email=current.email,
            phone=current.phone,
            role=current.role,
            status=current.status,  # type: ignore[arg-type]
            created_at=session.get("user", {}).get("created_at") or "1970-01-01T00:00:00Z",
        ),
    )


@router.post("/auth/logout")
async def logout(user: CurrentUserDep, request: Request) -> dict:
    settings = get_settings()
    auth_header = request.headers.get("authorization", "")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{settings.supabase_url}/auth/v1/logout",
                headers={
                    "apikey": settings.supabase_service_key,
                    "authorization": auth_header,
                },
            )
    except httpx.HTTPError:
        logger.warning("GoTrue logout call failed; session expires naturally")
    return {"status": "ok"}


class MeResponse(BaseModel):
    id: str
    full_name: str
    email: str
    phone: str | None
    role: str
    assigned_cases: list[Case]


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep, conn: Db) -> MeResponse:
    rows = await conn.fetch(
        """
        SELECT c.id, c.title, c.client_name, c.case_number, c.court, c.case_type,
               c.status, c.created_by, c.created_at
        FROM cases c
        JOIN case_assignments ca ON ca.case_id = c.id
        WHERE ca.user_id = $1
        ORDER BY c.created_at DESC
        """,
        user.id,
    )
    return MeResponse(
        id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        assigned_cases=[Case(**dict(r)) for r in rows],
    )
