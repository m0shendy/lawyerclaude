"""Platform admin console API — /admin/* (feature 003).

Authentication chain (fail-closed):
  POST /admin/login → POST /admin/mfa/verify → every other /admin/* via require_operator.
  Firm-role tokens on any /admin/* path ⇒ 403 + audit row (FR-303). [C-I][C-III]
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.db import get_service_pool
from app.core.errors import ApiError
from app.core.operator import (
    OperatorDep,
    audit_admin_read,
    require_operator,
    service_admin_conn,
)
from app.models.admin import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminMeResponse,
    AdminMfaVerifyRequest,
    AdminMfaVerifyResponse,
    AuditLogItem,
    BillingEventItem,
    BillingEventResolutionResponse,
    BillingEventResolveRequest,
    ChangePlanRequest,
    ConfirmRequest,
    ExtendTrialRequest,
    FirmDetail,
    FirmListItem,
    FirmStatusResponse,
    FirmUsage,
    HealthResponse,
    ManualPaymentRequest,
    ManualPaymentResponse,
    PlanChangeResponse,
    SubscriptionItem,
    TrialExtendResponse,
    WahaSession,
    WorkerHeartbeat,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_LOCKOUT_WINDOW_MINUTES = 15
_LOCKOUT_THRESHOLD = 5


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _check_lockout(pool, email: str) -> None:
    """Raise 423 if ≥5 failures for email in the last 15 min with no intervening success."""
    conn = await pool.acquire()
    try:
        rows = await conn.fetch(
            """
            SELECT succeeded
            FROM operator_login_attempts
            WHERE email = $1
              AND attempted_at > now() - interval '15 minutes'
            ORDER BY attempted_at DESC
            """,
            email,
        )
        failures = 0
        for row in rows:
            if row["succeeded"]:
                break  # intervening success resets window
            failures += 1
        if failures >= _LOCKOUT_THRESHOLD:
            raise ApiError(423, "locked", "تم قفل الحساب مؤقتاً — حاول مجدداً بعد 15 دقيقة")
    finally:
        await pool.release(conn)


async def _record_attempt(pool, email: str, succeeded: bool, origin_ip: str | None) -> None:
    conn = await pool.acquire()
    try:
        await conn.execute(
            "INSERT INTO operator_login_attempts (email, succeeded, origin_ip) VALUES ($1, $2, $3)",
            email,
            succeeded,
            origin_ip,
        )
    finally:
        await pool.release(conn)


async def _audit_login(pool, email: str, succeeded: bool, origin_ip: str | None) -> None:
    conn = await pool.acquire()
    try:
        await conn.execute(
            """
            INSERT INTO audit_log (who_role, entity_table, action, context)
            VALUES ('platform_operator', 'operator_login', 'create', $1)
            """,
            f"login {'success' if succeeded else 'failure'} for {email} from {origin_ip}",
        )
    except Exception:
        pass  # best-effort
    finally:
        await pool.release(conn)


# ─── POST /admin/login ────────────────────────────────────────────────────────

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(body: AdminLoginRequest, request: Request) -> AdminLoginResponse:
    """
    Backend-proxied login with lockout (R3). Never exposes GoTrue internals.
    Every attempt is recorded in operator_login_attempts and audit_log. [C-III]
    """
    settings = get_settings()
    pool = await get_service_pool()
    origin_ip = request.client.host if request.client else None

    await _check_lockout(pool, body.email)

    # Server-side GoTrue password grant
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": settings.supabase_service_key},
            json={"email": body.email, "password": body.password},
        )

    if resp.status_code != 200:
        await _record_attempt(pool, body.email, False, origin_ip)
        await _audit_login(pool, body.email, False, origin_ip)
        raise ApiError(401, "invalid_credentials", "بيانات الدخول غير صحيحة")

    session = resp.json()
    auth_user_id = session.get("user", {}).get("id")
    if not auth_user_id:
        await _record_attempt(pool, body.email, False, origin_ip)
        raise ApiError(401, "invalid_credentials", "بيانات الدخول غير صحيحة")

    # Record success (resets lockout window)
    await _record_attempt(pool, body.email, True, origin_ip)
    await _audit_login(pool, body.email, True, origin_ip)

    # List TOTP factors for this user
    access_token = session.get("access_token", "")
    async with httpx.AsyncClient(timeout=10) as client:
        factors_resp = await client.get(
            f"{settings.supabase_url}/auth/v1/factors",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {access_token}",
            },
        )

    if factors_resp.status_code != 200:
        return AdminLoginResponse(mfa_required=False, mfa_enrollment_required=True)

    factors = factors_resp.json()
    totp_factors = [f for f in factors if f.get("factor_type") == "totp" and f.get("status") == "verified"]

    if not totp_factors:
        return AdminLoginResponse(mfa_required=False, mfa_enrollment_required=True)

    factor_id = totp_factors[0]["id"]

    # Create MFA challenge
    async with httpx.AsyncClient(timeout=10) as client:
        challenge_resp = await client.post(
            f"{settings.supabase_url}/auth/v1/factors/{factor_id}/challenge",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {access_token}",
            },
        )

    if challenge_resp.status_code != 200:
        raise ApiError(500, "mfa_error", "فشل في إنشاء تحدي المصادقة")

    challenge_data = challenge_resp.json()
    challenge_id = challenge_data.get("id", "")

    # Encode both tokens into the challenge_token field so the verify step has them
    import json, base64
    bundle = base64.b64encode(
        json.dumps({"access_token": access_token, "challenge_id": challenge_id}).encode()
    ).decode()

    return AdminLoginResponse(
        mfa_required=True,
        factor_id=factor_id,
        challenge_token=bundle,
    )


# ─── POST /admin/mfa/enroll ───────────────────────────────────────────────────

@router.post("/mfa/enroll")
async def admin_mfa_enroll(request: Request) -> dict:
    """
    Initiate TOTP enrollment for a fresh operator account.
    Requires a valid aal1 token in Authorization (from a successful /admin/login
    that returned mfa_enrollment_required=true).
    """
    settings = get_settings()
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise ApiError(401, "unauthorized", "")

    access_token = auth_header.split(" ", 1)[1]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/factors",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {access_token}",
            },
            json={"factor_type": "totp", "issuer": "LawyerCloud Admin"},
        )

    if resp.status_code not in (200, 201):
        raise ApiError(500, "enroll_error", "فشل في إنشاء عامل المصادقة")

    data = resp.json()
    return {
        "factor_id": data.get("id"),
        "totp_uri": data.get("totp", {}).get("qr_code"),
        "totp_secret": data.get("totp", {}).get("secret"),
    }


# ─── POST /admin/mfa/verify ───────────────────────────────────────────────────

@router.post("/mfa/verify", response_model=AdminMfaVerifyResponse)
async def admin_mfa_verify(
    body: AdminMfaVerifyRequest,
    request: Request,
) -> AdminMfaVerifyResponse:
    """
    Verify TOTP code → obtain aal2 token → check allowlist → create session.
    On success: INSERT operator_sessions + audit row. [C-III]
    """
    import json, base64

    settings = get_settings()
    pool = await get_service_pool()
    origin_ip = request.client.host if request.client else None

    # Decode the challenge bundle from login
    try:
        bundle = json.loads(base64.b64decode(body.challenge_token).decode())
        access_token = bundle["access_token"]
        challenge_id = bundle["challenge_id"]
    except Exception:
        raise ApiError(400, "bad_request", "challenge_token غير صالح")

    # Verify via GoTrue
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/factors/{body.factor_id}/verify",
            headers={
                "apikey": settings.supabase_service_key,
                "Authorization": f"Bearer {access_token}",
            },
            json={"challenge_id": challenge_id, "code": body.code},
        )

    if resp.status_code != 200:
        raise ApiError(401, "invalid_code", "رمز المصادقة غير صحيح")

    session = resp.json()
    aal2_token = session.get("access_token", "")
    expires_in = session.get("expires_in", 3600)

    # Decode the aal2 token to get session_id and sub
    from app.core.security import _decode_token
    claims = _decode_token(aal2_token)
    auth_user_id = claims.get("sub")
    session_id = claims.get("session_id") or claims.get("jti")

    if not auth_user_id or not session_id:
        raise ApiError(500, "token_error", "خطأ في رمز الجلسة")

    # Allowlist check
    conn = await pool.acquire()
    try:
        op_row = await conn.fetchrow(
            "SELECT auth_user_id, display_name, is_active FROM platform_operators WHERE auth_user_id = $1",
            UUID(auth_user_id),
        )
        if op_row is None or not op_row["is_active"]:
            raise ApiError(403, "forbidden", "")

        # Create operator session
        await conn.execute(
            "INSERT INTO operator_sessions (session_id, operator_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            session_id,
            UUID(auth_user_id),
        )

        # Audit login success
        await conn.execute(
            """
            INSERT INTO audit_log (who_user_id, who_role, entity_table, action, context)
            VALUES ($1, 'platform_operator', 'operator_sessions', 'create', $2)
            """,
            UUID(auth_user_id),
            f"operator session created from {origin_ip}",
        )
    finally:
        await pool.release(conn)

    return AdminMfaVerifyResponse(access_token=aal2_token, expires_in=expires_in)


# ─── GET /admin/me ────────────────────────────────────────────────────────────

@router.get("/me", response_model=AdminMeResponse)
async def admin_me(operator: OperatorDep) -> AdminMeResponse:
    """Probe endpoint used by the session guard and the isolation suite."""
    pool = await get_service_pool()
    conn = await pool.acquire()
    try:
        sess = await conn.fetchrow(
            "SELECT created_at FROM operator_sessions WHERE session_id = $1",
            operator.session_id,
        )
    finally:
        await pool.release(conn)

    return AdminMeResponse(
        operator_id=operator.operator_id,
        display_name=operator.display_name,
        session_created_at=sess["created_at"] if sess else datetime.now(tz=timezone.utc),
    )


# ─── POST /admin/logout ───────────────────────────────────────────────────────

@router.post("/logout", status_code=204)
async def admin_logout(operator: OperatorDep) -> Response:
    """Delete own session row and write audit row."""
    pool = await get_service_pool()
    conn = await pool.acquire()
    try:
        await conn.execute(
            "DELETE FROM operator_sessions WHERE session_id = $1",
            operator.session_id,
        )
        await conn.execute(
            """
            INSERT INTO audit_log (who_user_id, who_role, entity_table, action, context)
            VALUES ($1, 'platform_operator', 'operator_sessions', 'delete', 'admin:logout')
            """,
            operator.operator_id,
        )
    finally:
        await pool.release(conn)
    return Response(status_code=204)


# ─── POST /admin/sessions/revoke-all ─────────────────────────────────────────

@router.post("/sessions/revoke-all", status_code=204)
async def admin_revoke_all(operator: OperatorDep) -> Response:
    """Delete ALL operator sessions (incident response) + audit row."""
    pool = await get_service_pool()
    conn = await pool.acquire()
    try:
        deleted = await conn.execute(
            "DELETE FROM operator_sessions WHERE operator_id = $1",
            operator.operator_id,
        )
        await conn.execute(
            """
            INSERT INTO audit_log (who_user_id, who_role, entity_table, action, context)
            VALUES ($1, 'platform_operator', 'operator_sessions', 'delete', $2)
            """,
            operator.operator_id,
            f"revoke-all: {deleted}",
        )
    finally:
        await pool.release(conn)
    return Response(status_code=204)


# ═══════════════════════════════════════════════════════════════════════════════
# US2 — All-Firms Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_attention_flags(firm: dict, now: datetime) -> list[str]:
    flags: list[str] = []
    trial_ends = firm.get("trial_ends_at")
    if trial_ends and firm.get("status") == "trial":
        from datetime import timedelta
        if trial_ends <= now + timedelta(days=3):
            flags.append("trial_expiring")
    sub_status = firm.get("sub_status")
    if sub_status == "past_due":
        flags.append("payment_failed")
    if firm.get("unresolved_events"):
        flags.append("unprocessed_event")
    return flags


@router.get("/firms", response_model=list[FirmListItem])
async def admin_list_firms(
    operator: OperatorDep,
    status: str | None = None,
    plan: str | None = None,
    q: str | None = None,
    page: int = 1,
) -> list[FirmListItem]:
    """List all firms with subscription + attention flags. Metadata only. [FR-310]"""
    now = datetime.now(tz=timezone.utc)
    async with service_admin_conn(operator) as conn:
        rows = await conn.fetch(
            """
            SELECT
                f.id, f.name, f.slug, f.status, f.trial_ends_at, f.created_at,
                s.plan, s.status AS sub_status,
                EXISTS (
                    SELECT 1 FROM billing_events be
                    WHERE be.processed_at IS NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM billing_event_resolutions ber
                          WHERE ber.billing_event_id = be.id
                      )
                ) AS unresolved_events
            FROM firms f
            LEFT JOIN LATERAL (
                SELECT plan, status FROM subscriptions
                WHERE firm_id = f.id ORDER BY created_at DESC LIMIT 1
            ) s ON true
            WHERE ($1::text IS NULL OR f.status = $1)
              AND ($2::text IS NULL OR s.plan = $2)
              AND ($3::text IS NULL OR f.name ILIKE '%' || $3 || '%' OR f.slug ILIKE '%' || $3 || '%')
            ORDER BY f.created_at DESC
            LIMIT 50 OFFSET ($4 - 1) * 50
            """,
            status, plan, q, page,
        )

    return [
        FirmListItem(
            id=r["id"],
            name=r["name"],
            slug=r["slug"],
            status=r["status"],
            plan=r["plan"],
            trial_ends_at=r["trial_ends_at"],
            created_at=r["created_at"],
            attention_flags=_compute_attention_flags(dict(r), now),
        )
        for r in rows
    ]


@router.get("/firms/{firm_id}", response_model=FirmDetail)
async def admin_get_firm(firm_id: UUID, operator: OperatorDep) -> FirmDetail:
    """Firm detail + usage counts. Writes admin_read audit row. [FR-311]"""
    async with service_admin_conn(operator) as conn:
        firm = await conn.fetchrow(
            """
            SELECT f.id, f.name, f.slug, f.status, f.trial_ends_at, f.created_at,
                   s.plan, s.status AS sub_status, s.current_period_end, s.provider
            FROM firms f
            LEFT JOIN LATERAL (
                SELECT plan, status, current_period_end, provider
                FROM subscriptions WHERE firm_id = f.id ORDER BY created_at DESC LIMIT 1
            ) s ON true
            WHERE f.id = $1
            """,
            firm_id,
        )
        if not firm:
            raise ApiError(404, "not_found", "المكتب غير موجود")

        usage = await conn.fetchrow(
            "SELECT user_count, case_count, document_count, storage_bytes, ai_output_count, last_activity_at "
            "FROM admin_firm_usage WHERE firm_id = $1",
            firm_id,
        )

        await audit_admin_read(conn, "firms", firm_id, firm_id, operator)

    sub = None
    if firm["plan"]:
        sub = {
            "plan": firm["plan"],
            "status": firm["sub_status"],
            "current_period_end": firm["current_period_end"],
            "provider": firm["provider"],
        }

    return FirmDetail(
        id=firm["id"],
        name=firm["name"],
        slug=firm["slug"],
        status=firm["status"],
        plan=firm["plan"],
        trial_ends_at=firm["trial_ends_at"],
        created_at=firm["created_at"],
        subscription=sub,
        usage=FirmUsage(
            user_count=usage["user_count"] if usage else 0,
            case_count=usage["case_count"] if usage else 0,
            document_count=usage["document_count"] if usage else 0,
            storage_bytes=usage["storage_bytes"] if usage else 0,
            ai_output_count=usage["ai_output_count"] if usage else 0,
            last_activity_at=usage["last_activity_at"] if usage else None,
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# US3 — Firm Lifecycle Management
# ═══════════════════════════════════════════════════════════════════════════════

async def _get_firm_status(conn, firm_id: UUID) -> str:
    row = await conn.fetchrow("SELECT status FROM firms WHERE id = $1", firm_id)
    if not row:
        raise ApiError(404, "not_found", "المكتب غير موجود")
    return row["status"]


async def _update_firm_status(conn, firm_id: UUID, new_status: str, operator_id: UUID) -> None:
    await conn.execute(
        "UPDATE firms SET status = $1 WHERE id = $2",
        new_status, firm_id,
    )


@router.post("/firms/{firm_id}/suspend", response_model=FirmStatusResponse)
async def admin_suspend_firm(firm_id: UUID, body: ConfirmRequest, operator: OperatorDep) -> FirmStatusResponse:
    async with service_admin_conn(operator) as conn:
        current = await _get_firm_status(conn, firm_id)
        if current == "suspended":
            raise ApiError(409, "conflict", "المكتب موقوف بالفعل")
        await _update_firm_status(conn, firm_id, "suspended", operator.operator_id)
    return FirmStatusResponse(status="suspended")


@router.post("/firms/{firm_id}/reactivate", response_model=FirmStatusResponse)
async def admin_reactivate_firm(firm_id: UUID, body: ConfirmRequest, operator: OperatorDep) -> FirmStatusResponse:
    async with service_admin_conn(operator) as conn:
        current = await _get_firm_status(conn, firm_id)
        if current not in ("suspended", "past_due"):
            raise ApiError(409, "conflict", "المكتب ليس في حالة تتطلب إعادة تفعيل")
        await _update_firm_status(conn, firm_id, "active", operator.operator_id)
    return FirmStatusResponse(status="active")


@router.post("/firms/{firm_id}/cancel", response_model=FirmStatusResponse)
async def admin_cancel_firm(firm_id: UUID, body: ConfirmRequest, operator: OperatorDep) -> FirmStatusResponse:
    async with service_admin_conn(operator) as conn:
        current = await _get_firm_status(conn, firm_id)
        if current == "cancelled":
            raise ApiError(409, "conflict", "المكتب ملغى بالفعل")
        await _update_firm_status(conn, firm_id, "cancelled", operator.operator_id)
    return FirmStatusResponse(status="cancelled")


@router.post("/firms/{firm_id}/extend-trial", response_model=TrialExtendResponse)
async def admin_extend_trial(firm_id: UUID, body: ExtendTrialRequest, operator: OperatorDep) -> TrialExtendResponse:
    async with service_admin_conn(operator) as conn:
        row = await conn.fetchrow("SELECT status, trial_ends_at FROM firms WHERE id = $1", firm_id)
        if not row:
            raise ApiError(404, "not_found", "المكتب غير موجود")
        if row["status"] == "cancelled":
            raise ApiError(422, "invalid_state", "لا يمكن تمديد تجربة مكتب ملغى [FR-321]")
        new_end = await conn.fetchval(
            "UPDATE firms SET trial_ends_at = trial_ends_at + ($1 * interval '1 day') "
            "WHERE id = $2 RETURNING trial_ends_at",
            body.days, firm_id,
        )
    return TrialExtendResponse(trial_ends_at=new_end)


@router.post("/firms/{firm_id}/change-plan", response_model=PlanChangeResponse)
async def admin_change_plan(firm_id: UUID, body: ChangePlanRequest, operator: OperatorDep) -> PlanChangeResponse:
    """Update subscription plan only — moves no money (FR-322)."""
    async with service_admin_conn(operator) as conn:
        row = await conn.fetchrow("SELECT id FROM firms WHERE id = $1", firm_id)
        if not row:
            raise ApiError(404, "not_found", "المكتب غير موجود")
        updated = await conn.execute(
            "UPDATE subscriptions SET plan = $1 WHERE firm_id = $2",
            body.plan, firm_id,
        )
        if updated == "UPDATE 0":
            raise ApiError(404, "not_found", "لا يوجد اشتراك لهذا المكتب")
    return PlanChangeResponse(plan=body.plan)


# ─── US4: Billing & Subscription Oversight (T024 + T025) ─────────────────────

@router.get("/subscriptions", response_model=list[SubscriptionItem])
async def admin_list_subscriptions(
    operator: OperatorDep,
    status: str | None = None,
    firm_id: UUID | None = None,
) -> list[SubscriptionItem]:
    """List subscriptions with optional status/firm filters."""
    async with service_admin_conn(operator) as conn:
        clauses = []
        params: list = []
        if status:
            params.append(status)
            clauses.append(f"s.status = ${len(params)}")
        if firm_id:
            params.append(firm_id)
            clauses.append(f"s.firm_id = ${len(params)}")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = await conn.fetch(
            f"""
            SELECT s.id, s.firm_id, f.name AS firm_name, s.plan, s.status,
                   s.provider, s.current_period_end, s.created_at
              FROM subscriptions s
              JOIN firms f ON f.id = s.firm_id
             {where}
             ORDER BY s.created_at DESC
            """,
            *params,
        )
    return [SubscriptionItem(**dict(r)) for r in rows]


@router.get("/billing-events", response_model=list[BillingEventItem])
async def admin_list_billing_events(
    operator: OperatorDep,
    unprocessed: bool = False,
) -> list[BillingEventItem]:
    """List billing events; ?unprocessed=true limits to unresolved queue."""
    async with service_admin_conn(operator) as conn:
        extra = "AND be.processed_at IS NULL" if unprocessed else ""
        rows = await conn.fetch(
            f"""
            SELECT be.id, be.event_type, be.provider, be.provider_ref,
                   be.amount_cents, be.payload, be.processed_at, be.created_at,
                   (ber.id IS NOT NULL)  AS resolved,
                   ber.note              AS resolution_note
              FROM billing_events be
         LEFT JOIN billing_event_resolutions ber ON ber.billing_event_id = be.id
             WHERE 1=1 {extra}
             ORDER BY be.created_at DESC
             LIMIT 200
            """,
        )
    return [
        BillingEventItem(
            id=r["id"],
            event_type=r["event_type"],
            provider=r["provider"],
            provider_ref=r["provider_ref"],
            amount_cents=r["amount_cents"],
            payload=r["payload"] if isinstance(r["payload"], dict) else None,
            processed_at=r["processed_at"],
            created_at=r["created_at"],
            resolved=r["resolved"],
            resolution_note=r["resolution_note"],
        )
        for r in rows
    ]


@router.post("/billing-events/{event_id}/resolve", response_model=BillingEventResolutionResponse)
async def admin_resolve_billing_event(
    event_id: UUID,
    body: BillingEventResolveRequest,
    operator: OperatorDep,
) -> BillingEventResolutionResponse:
    """Insert resolution note — billing_events row is NEVER updated. [C-III]"""
    async with service_admin_conn(operator) as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM billing_events WHERE id = $1", event_id
        )
        if not existing:
            raise ApiError(404, "not_found", "حدث الفوترة غير موجود")
        already = await conn.fetchrow(
            "SELECT id FROM billing_event_resolutions WHERE billing_event_id = $1", event_id
        )
        if already:
            raise ApiError(409, "already_resolved", "تم معالجة هذا الحدث بالفعل")
        resolution_id = await conn.fetchval(
            """
            INSERT INTO billing_event_resolutions (billing_event_id, note, resolved_by)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            event_id, body.note.strip(), operator.operator_id,
        )
    return BillingEventResolutionResponse(resolution_id=resolution_id)


@router.post("/firms/{firm_id}/manual-payment", response_model=ManualPaymentResponse)
async def admin_manual_payment(
    firm_id: UUID,
    body: ManualPaymentRequest,
    operator: OperatorDep,
) -> ManualPaymentResponse:
    """Record a manual payment and activate the firm's subscription."""
    from app.billing.activation import activate_subscription  # noqa: PLC0415
    async with service_admin_conn(operator) as conn:
        row = await conn.fetchrow("SELECT id FROM firms WHERE id = $1", firm_id)
        if not row:
            raise ApiError(404, "not_found", "المكتب غير موجود")
        sub = await conn.fetchrow(
            "SELECT plan FROM subscriptions WHERE firm_id = $1", firm_id
        )
        if not sub:
            raise ApiError(404, "not_found", "لا يوجد اشتراك لهذا المكتب")
        plan = sub["plan"] or "basic"
        payment_id = await conn.fetchval(
            """
            INSERT INTO manual_payments (firm_id, amount_egp, paid_date, reference, note, recorded_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            firm_id, body.amount_egp, body.paid_date, body.reference.strip(),
            body.note.strip(), operator.operator_id,
        )
        await activate_subscription(conn, firm_id, plan, provider="manual")
        firm_row = await conn.fetchrow("SELECT status FROM firms WHERE id = $1", firm_id)
    return ManualPaymentResponse(
        payment_id=payment_id,
        subscription_status="active",
        firm_status=firm_row["status"],
    )


# ─── US5: Platform Audit Log Viewer (T028) ────────────────────────────────────

@router.get("/audit", response_model=list[AuditLogItem])
async def admin_audit_log(
    operator: OperatorDep,
    firm_id: UUID | None = None,
    actor: str | None = None,
    entity: str | None = None,
    action: str | None = None,
    platform_only: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 0,
    page_size: int = 50,
) -> list[AuditLogItem]:
    """Paginated platform-wide audit log with filters. Every query is self-logged."""
    async with service_admin_conn(operator) as conn:
        clauses: list[str] = []
        params: list = []

        if firm_id:
            params.append(firm_id)
            clauses.append(f"al.firm_id = ${len(params)}")
        if actor:
            params.append(actor)
            clauses.append(f"al.actor_id::text ILIKE ${len(params)}")
        if entity:
            params.append(entity)
            clauses.append(f"al.entity = ${len(params)}")
        if action:
            params.append(action)
            clauses.append(f"al.action = ${len(params)}")
        if platform_only:
            clauses.append("al.context = 'platform_admin'")
        if date_from:
            params.append(date_from)
            clauses.append(f"al.when_ts >= ${len(params)}::timestamptz")
        if date_to:
            params.append(date_to)
            clauses.append(f"al.when_ts <= ${len(params)}::timestamptz")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([page_size, page * page_size])
        rows = await conn.fetch(
            f"""
            SELECT al.id, al.firm_id, al.actor_id, al.actor_role, al.context,
                   al.entity, al.record_id, al.action, al.old_data, al.new_data, al.when_ts
              FROM audit_log al
             {where}
             ORDER BY al.when_ts DESC
             LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        await audit_admin_read(
            conn, "audit_log",
            str(firm_id) if firm_id else None,
            None,
            operator,
        )
    return [AuditLogItem(**dict(r)) for r in rows]


# ─── US6: Operational Health (T031) ──────────────────────────────────────────

import asyncio  # noqa: E402  (module-level import would be cleaner but this keeps the endpoint self-contained)
from datetime import timedelta

_waha_cache: tuple[float, list[WahaSession] | None] | None = None
_WAHA_CACHE_TTL = 30.0


@router.get("/health", response_model=HealthResponse)
async def admin_health(operator: OperatorDep) -> HealthResponse:
    """Worker heartbeats + WAHA sessions + recent signups."""
    global _waha_cache  # noqa: PLW0603

    import time  # noqa: PLC0415
    settings = get_settings()
    now_ts = time.monotonic()

    async with service_admin_conn(operator) as conn:
        hb_rows = await conn.fetch(
            "SELECT worker_name, last_beat, details FROM worker_heartbeats ORDER BY worker_name"
        )
        signup_rows = await conn.fetch(
            "SELECT id, name, slug, status, created_at FROM firms ORDER BY created_at DESC LIMIT 10"
        )

    stale_threshold = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    workers = [
        WorkerHeartbeat(
            worker_name=r["worker_name"],
            last_beat=r["last_beat"],
            stale=(r["last_beat"] is None or r["last_beat"] < stale_threshold),
            details=r["details"],
        )
        for r in hb_rows
    ]

    waha_sessions: list[WahaSession] | None = None
    waha_warning: str | None = None

    if _waha_cache and (now_ts - _waha_cache[0]) < _WAHA_CACHE_TTL:
        waha_sessions = _waha_cache[1]
    else:
        waha_url = getattr(settings, "WAHA_URL", None)
        waha_key = getattr(settings, "WAHA_API_KEY", None)
        if waha_url:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    headers = {"X-Api-Key": waha_key} if waha_key else {}
                    resp = await client.get(f"{waha_url}/api/sessions", headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    waha_sessions = [
                        WahaSession(
                            firm_slug=s.get("name", ""),
                            state=s.get("status", "unknown"),
                        )
                        for s in data
                    ]
                    _waha_cache = (now_ts, waha_sessions)
            except Exception as exc:
                waha_warning = f"WAHA unreachable: {exc}"
                _waha_cache = (now_ts, None)
        else:
            waha_warning = "WAHA_URL not configured"

    recent_signups = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "slug": r["slug"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in signup_rows
    ]

    return HealthResponse(
        workers=workers,
        waha_sessions=waha_sessions,
        waha_warning=waha_warning,
        recent_signups=recent_signups,
    )
