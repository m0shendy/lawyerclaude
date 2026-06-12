"""Pydantic models for the platform admin console (feature 003).

Covers: login/MFA payloads, lifecycle actions, billing, and response schemas
per contracts/rest-api.md.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_validator


# ─── Auth / Login ─────────────────────────────────────────────────────────────

class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminLoginResponse(BaseModel):
    mfa_required: bool
    factor_id: str | None = None
    challenge_token: str | None = None
    mfa_enrollment_required: bool = False


class AdminMfaVerifyRequest(BaseModel):
    factor_id: str
    challenge_token: str
    code: str


class AdminMfaVerifyResponse(BaseModel):
    access_token: str
    expires_in: int


class AdminMeResponse(BaseModel):
    operator_id: UUID
    display_name: str
    session_created_at: datetime


# ─── Lifecycle actions ────────────────────────────────────────────────────────

class ConfirmRequest(BaseModel):
    """Base for any action that requires confirm: true."""
    confirm: bool

    @field_validator("confirm")
    @classmethod
    def must_be_true(cls, v: bool) -> bool:
        if not v:
            raise ValueError("confirm must be true")
        return v


class ExtendTrialRequest(ConfirmRequest):
    days: int

    @field_validator("days")
    @classmethod
    def days_range(cls, v: int) -> int:
        if not (1 <= v <= 90):
            raise ValueError("days must be between 1 and 90")
        return v


class ChangePlanRequest(ConfirmRequest):
    plan: str


class FirmStatusResponse(BaseModel):
    status: str


class TrialExtendResponse(BaseModel):
    trial_ends_at: datetime | None


class PlanChangeResponse(BaseModel):
    plan: str


# ─── Billing ─────────────────────────────────────────────────────────────────

class BillingEventResolveRequest(BaseModel):
    note: str

    @field_validator("note")
    @classmethod
    def note_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("note is required")
        return v


class ManualPaymentRequest(ConfirmRequest):
    amount_egp: Decimal
    paid_date: date
    reference: str
    note: str

    @field_validator("amount_egp")
    @classmethod
    def positive_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount_egp must be positive")
        return v

    @field_validator("note", "reference")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field is required")
        return v


class ManualPaymentResponse(BaseModel):
    payment_id: UUID
    subscription_status: str
    firm_status: str


class BillingEventResolutionResponse(BaseModel):
    resolution_id: UUID


# ─── Firm list / detail ───────────────────────────────────────────────────────

class FirmUsage(BaseModel):
    user_count: int
    case_count: int
    document_count: int
    storage_bytes: int
    ai_output_count: int
    last_activity_at: datetime | None


class FirmListItem(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    plan: str | None
    trial_ends_at: datetime | None
    created_at: datetime
    attention_flags: list[str]


class FirmDetail(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    plan: str | None
    trial_ends_at: datetime | None
    created_at: datetime
    subscription: dict | None
    usage: FirmUsage


# ─── Subscription / billing event list ───────────────────────────────────────

class SubscriptionItem(BaseModel):
    id: UUID
    firm_id: UUID
    firm_name: str
    plan: str | None
    status: str
    provider: str | None
    current_period_end: datetime | None
    created_at: datetime


class BillingEventItem(BaseModel):
    id: UUID
    event_type: str
    provider: str | None
    provider_ref: str | None
    amount_cents: int | None
    payload: dict | None
    processed_at: datetime | None
    created_at: datetime
    resolved: bool
    resolution_note: str | None


# ─── Audit log ───────────────────────────────────────────────────────────────

class AuditLogItem(BaseModel):
    id: UUID
    firm_id: UUID | None
    actor_id: UUID | None
    actor_role: str | None
    context: str | None
    entity: str | None
    record_id: UUID | None
    action: str
    old_data: dict | None
    new_data: dict | None
    when_ts: datetime


# ─── Health ──────────────────────────────────────────────────────────────────

class WorkerHeartbeat(BaseModel):
    worker_name: str
    last_beat: datetime | None
    stale: bool
    details: dict | None


class WahaSession(BaseModel):
    firm_slug: str
    state: str


class HealthResponse(BaseModel):
    workers: list[WorkerHeartbeat]
    waha_sessions: list[WahaSession] | None
    waha_warning: str | None
    recent_signups: list[dict]
