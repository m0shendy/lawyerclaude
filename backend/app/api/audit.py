"""Audit log viewer endpoint (T036). [C-III]

Manager-only, READ-ONLY view over the append-only audit_log. There are no
mutation endpoints here by design — the log is written exclusively by DB
triggers and `REVOKE UPDATE, DELETE` makes it tamper-proof at the DB level.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.audit.audit import fetch_audit_entries
from app.core.db import Db
from app.core.rbac import MANAGER, require_roles
from app.models import AuditEntry

logger = logging.getLogger(__name__)

router = APIRouter()


class AuditLogResponse(BaseModel):
    entries: list[AuditEntry]
    limit: int
    offset: int


def _coerce_change_detail(entry: dict[str, Any]) -> dict[str, Any]:
    """asyncpg returns jsonb as text unless a codec is registered — decode it."""
    detail = entry.get("change_detail")
    if isinstance(detail, str):
        try:
            entry["change_detail"] = json.loads(detail)
        except ValueError:
            entry["change_detail"] = None
    return entry


@router.get(
    "/audit-log",
    response_model=AuditLogResponse,
    dependencies=[Depends(require_roles(MANAGER))],
)
async def get_audit_log(
    conn: Db,
    entity_table: str | None = Query(default=None),
    record_id: UUID | None = Query(default=None),
    who_user_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditLogResponse:
    entries = await fetch_audit_entries(
        conn,
        entity_table=entity_table,
        record_id=record_id,
        who_user_id=who_user_id,
        limit=limit,
        offset=offset,
    )
    return AuditLogResponse(
        entries=[AuditEntry(**_coerce_change_detail(e)) for e in entries],
        limit=limit,
        offset=offset,
    )
