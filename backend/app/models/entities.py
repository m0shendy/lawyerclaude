"""Entity models (T023) — pydantic v2, field names exactly match DB columns.

One source of truth for API payload shapes; enums as Literal aliases per the
conventions doc. The DB schema (supabase/migrations/0002) is authoritative.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ── enums ─────────────────────────────────────────────────────────────────────

Role = Literal["partner_manager", "lawyer", "paralegal", "secretary"]
UserStatus = Literal["active", "inactive"]
DocumentSourceType = Literal["text_pdf", "scanned"]
DocumentStatus = Literal["pending", "processing", "ready", "low_confidence", "failed"]
AiOutputType = Literal["summary", "extraction", "analysis", "clause_flag", "risk_signal"]
ReviewState = Literal["draft_unreviewed", "approved"]
DeadlineType = Literal["general", "appeal_istinaf", "mu_arada", "naqd"]
TaskStatus = Literal["open", "in_progress", "done", "cancelled"]
NotificationStatus = Literal["sent", "failed", "skipped"]
ReportType = Literal["daily_what_happened", "tomorrow_tasks"]

APPEAL_TYPES: tuple[str, ...] = ("appeal_istinaf", "mu_arada", "naqd")

# ── grounding (source links → chunks) [C-V] ──────────────────────────────────


class SourceLink(BaseModel):
    chunk_id: UUID
    document_id: UUID
    page_ref: int | None = None


# ── users ─────────────────────────────────────────────────────────────────────


class User(BaseModel):
    id: UUID
    auth_user_id: UUID | None = None
    full_name: str
    email: str
    phone: str | None = None
    role: Role
    status: UserStatus
    created_at: datetime


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1)
    email: str
    phone: str | None = None
    role: Role
    password: str = Field(min_length=8)  # forwarded to GoTrue, never stored here


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    role: Role | None = None
    status: UserStatus | None = None


# ── cases ─────────────────────────────────────────────────────────────────────


class Case(BaseModel):
    id: UUID
    title: str
    client_name: str
    case_number: str | None = None
    court: str | None = None
    case_type: str | None = None
    status: str
    created_by: UUID | None = None
    created_at: datetime


class CaseCreate(BaseModel):
    title: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    case_number: str | None = None
    court: str | None = None
    case_type: str | None = None
    status: str = "open"


class CaseUpdate(BaseModel):
    title: str | None = None
    client_name: str | None = None
    case_number: str | None = None
    court: str | None = None
    case_type: str | None = None
    status: str | None = None


class CaseAssignment(BaseModel):
    id: UUID
    case_id: UUID
    user_id: UUID
    created_at: datetime


class AssignmentCreate(BaseModel):
    user_id: UUID


# ── documents ────────────────────────────────────────────────────────────────


class Document(BaseModel):
    id: UUID
    case_id: UUID
    file_path: str
    file_name: str
    source_type: DocumentSourceType
    status: DocumentStatus
    ocr_confidence: float | None = None
    error_detail: str | None = None
    uploaded_by: UUID | None = None
    uploaded_at: datetime


class DocumentChunk(BaseModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    chunk_text: str
    page_ref: int | None = None
    source_location: dict[str, Any] | None = None


# ── ai_outputs [C-II][C-V] ───────────────────────────────────────────────────


class AiOutput(BaseModel):
    id: UUID
    document_id: UUID | None = None
    case_id: UUID | None = None
    type: AiOutputType
    content: dict[str, Any]
    source_links: list[SourceLink]
    review_state: ReviewState
    low_confidence_flag: bool
    generated_by_model: str | None = None
    created_at: datetime
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    approved_version: int | None = None


# ── deadlines [C-X] ──────────────────────────────────────────────────────────


class Deadline(BaseModel):
    id: UUID
    case_id: UUID
    type: DeadlineType
    title: str
    basis: str | None = None
    due_date: date
    suggested_date: date | None = None
    confirmed: bool
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
    responsible_user_id: UUID
    derived_from_document_id: UUID | None = None
    low_confidence_flag: bool
    acknowledged_at: datetime | None = None
    created_at: datetime


class DeadlineCreate(BaseModel):
    """General deadlines only — appeal types are system-suggested, never user-created as fact. [C-X]"""

    title: str = Field(min_length=1)
    due_date: date
    responsible_user_id: UUID
    basis: str | None = None


class DeadlineUpdate(BaseModel):
    title: str | None = None
    due_date: date | None = None
    responsible_user_id: UUID | None = None
    basis: str | None = None


# ── tasks ─────────────────────────────────────────────────────────────────────


class Task(BaseModel):
    id: UUID
    case_id: UUID
    assigned_to: UUID
    description: str
    due_date: date | None = None
    status: TaskStatus
    created_at: datetime


class TaskCreate(BaseModel):
    assigned_to: UUID
    description: str = Field(min_length=1)
    due_date: date | None = None


class TaskUpdate(BaseModel):
    assigned_to: UUID | None = None
    description: str | None = None
    due_date: date | None = None
    status: TaskStatus | None = None


# ── logs ──────────────────────────────────────────────────────────────────────


class NotificationLogEntry(BaseModel):
    id: UUID
    deadline_id: UUID | None = None
    task_id: UUID | None = None
    recipient_user_id: UUID
    channel: str
    lead_point: str | None = None
    is_escalation: bool
    scheduled_for: datetime
    sent_at: datetime | None = None
    status: NotificationStatus
    error_detail: str | None = None


class ReportLogEntry(BaseModel):
    id: UUID
    type: ReportType
    recipient_user_id: UUID
    content: str | None = None
    items: list[dict[str, Any]]
    generated_at: datetime
    sent_at: datetime | None = None


class AuditEntry(BaseModel):
    id: int
    who_user_id: UUID | None = None
    who_role: str | None = None
    when_ts: datetime
    entity_table: str
    record_id: UUID | None = None
    action: str
    change_detail: dict[str, Any] | None = None
    context: str | None = None
