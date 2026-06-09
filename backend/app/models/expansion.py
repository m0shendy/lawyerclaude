"""Shared Pydantic base models for the legal platform expansion (spec 002).

ConstitutionNote (docstring):
    Every AI output MUST be created in `draft_unreviewed` state.
    It MUST NOT be exported, printed, attached as official, or sent to a
    client until a human explicitly clicks 'Reviewed & Approved.'
    No code path may bypass this gate. [C-II]

    Secret values (API keys, WAHA key) MUST NEVER appear in the audit log;
    only the action, actor, and timestamp are recorded. [C-III]
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Reusable limit/offset pagination parameters."""

    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0


class AuditedBase(BaseModel):
    """Base for any model row that carries creation metadata."""

    created_by: UUID | None = None
    created_at: datetime | None = None


class AuditedUpdateBase(BaseModel):
    """Base for models that carry update metadata."""

    updated_by: UUID | None = None
    updated_at: datetime | None = None
