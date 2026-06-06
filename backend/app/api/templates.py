"""Document Templates endpoints (Module D).

Endpoints
---------
  GET    /templates             — list active templates (filter: category)
  POST   /templates             — create template (manager only)
  GET    /templates/{id}        — detail
  PATCH  /templates/{id}        — update (manager only)
  POST   /templates/{id}/render — merge template with case context
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import MANAGER, require_roles
from app.core.security import CurrentUser, CurrentUserDep

logger = logging.getLogger(__name__)

router = APIRouter()

TemplateCategory = Literal[
    "contract", "pleading", "power_of_attorney",
    "letter", "memo", "notice", "court_submission", "other"
]

_TPL_COLS = (
    "id, is_platform, name_ar, category, content, merge_fields, "
    "is_active, version, created_by, created_at, updated_at"
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class MergeFieldDef(BaseModel):
    key: str
    label_ar: str
    type: Literal["text", "date", "number"] = "text"
    required: bool = True


class TemplateRead(BaseModel):
    id: UUID
    is_platform: bool
    name_ar: str
    category: TemplateCategory
    content: str
    merge_fields: list[MergeFieldDef]
    is_active: bool
    version: int
    created_by: UUID | None = None
    created_at: str
    updated_at: str


class TemplateSummary(BaseModel):
    """Slim version for list view — no content body."""
    id: UUID
    is_platform: bool
    name_ar: str
    category: TemplateCategory
    is_active: bool
    version: int
    merge_fields: list[MergeFieldDef]
    created_at: str


class TemplateCreate(BaseModel):
    name_ar: str
    category: TemplateCategory
    content: str
    merge_fields: list[MergeFieldDef] = []
    is_platform: bool = False


class TemplateUpdate(BaseModel):
    name_ar: str | None = None
    category: TemplateCategory | None = None
    content: str | None = None
    merge_fields: list[MergeFieldDef] | None = None
    is_active: bool | None = None


class RenderRequest(BaseModel):
    case_id: UUID | None = None
    overrides: dict[str, str] = {}


class RenderResponse(BaseModel):
    rendered: str
    unresolved_fields: list[str]


def _row(r) -> TemplateRead:
    d = dict(r)
    d["created_at"] = d["created_at"].isoformat()
    d["updated_at"] = d["updated_at"].isoformat()
    import json
    if isinstance(d["merge_fields"], str):
        d["merge_fields"] = json.loads(d["merge_fields"])
    return TemplateRead(**d)


def _summary_row(r) -> TemplateSummary:
    d = dict(r)
    d["created_at"] = d["created_at"].isoformat()
    import json
    if isinstance(d["merge_fields"], str):
        d["merge_fields"] = json.loads(d["merge_fields"])
    return TemplateSummary(**d)


# ── Template merge engine ─────────────────────────────────────────────────────

_SYSTEM_RESOLVERS: dict[str, Any] = {
    "today": lambda ctx: date.today().strftime("%Y/%m/%d"),
    "case_number": lambda ctx: ctx.get("case", {}).get("case_number") or "",
    "case_title": lambda ctx: ctx.get("case", {}).get("title") or "",
    "client_name_ar": lambda ctx: ctx.get("case", {}).get("client_name") or "",
    "court_name": lambda ctx: ctx.get("hearing", {}).get("court_name") or ctx.get("case", {}).get("court") or "",
    "hearing_date": lambda ctx: (ctx.get("hearing", {}).get("hearing_date") or ""),
}


def render_template(content: str, context: dict, overrides: dict[str, str]) -> RenderResponse:
    result = content
    resolved = {k: str(v(context)) for k, v in _SYSTEM_RESOLVERS.items()}
    resolved.update(overrides)

    for key, value in resolved.items():
        result = result.replace(f"{{{{{key}}}}}", value)

    unresolved = re.findall(r"\{\{(\w+)\}\}", result)
    return RenderResponse(rendered=result, unresolved_fields=unresolved)


# ── GET /templates ────────────────────────────────────────────────────────────

@router.get("/templates", response_model=list[TemplateSummary])
async def list_templates(
    user: CurrentUserDep,
    conn: Db,
    category: TemplateCategory | None = Query(None),
) -> list[TemplateSummary]:
    conditions = ["is_active = true"]
    params: list = []
    if category:
        params.append(category)
        conditions.append(f"category = ${len(params)}")
    where = f"WHERE {' AND '.join(conditions)}"
    rows = await conn.fetch(
        f"""
        SELECT id, is_platform, name_ar, category, is_active, version, merge_fields, created_at
        FROM document_templates {where} ORDER BY category, name_ar
        """,
        *params,
    )
    return [_summary_row(r) for r in rows]


# ── POST /templates ───────────────────────────────────────────────────────────

@router.post("/templates", response_model=TemplateRead, status_code=201)
async def create_template(
    body: TemplateCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER))],
) -> TemplateRead:
    import json
    r = await conn.fetchrow(
        f"""
        INSERT INTO document_templates
          (name_ar, category, content, merge_fields, is_platform, created_by)
        VALUES ($1,$2,$3,$4,$5,$6)
        RETURNING {_TPL_COLS}
        """,
        body.name_ar, body.category, body.content,
        json.dumps([mf.model_dump() for mf in body.merge_fields]),
        body.is_platform, user.id,
    )
    return _row(r)


# ── GET /templates/{id} ───────────────────────────────────────────────────────

@router.get("/templates/{template_id}", response_model=TemplateRead)
async def get_template(template_id: UUID, user: CurrentUserDep, conn: Db) -> TemplateRead:
    r = await conn.fetchrow(f"SELECT {_TPL_COLS} FROM document_templates WHERE id=$1", template_id)
    if r is None:
        raise ApiError(404, "not_found", "النموذج غير موجود")
    return _row(r)


# ── PATCH /templates/{id} ────────────────────────────────────────────────────

@router.patch("/templates/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: UUID,
    body: TemplateUpdate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER))],
) -> TemplateRead:
    import json
    existing_row = await conn.fetchrow(
        "SELECT id FROM document_templates WHERE id=$1", template_id
    )
    if existing_row is None:
        raise ApiError(404, "not_found", "النموذج غير موجود")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return await get_template(template_id, user, conn)

    # Serialize merge_fields if present
    if "merge_fields" in updates and updates["merge_fields"] is not None:
        updates["merge_fields"] = json.dumps([mf if isinstance(mf, dict) else mf.model_dump() for mf in updates["merge_fields"]])
    # Bump version on content change
    if "content" in updates:
        updates["version"] = await conn.fetchval(
            "SELECT version + 1 FROM document_templates WHERE id=$1", template_id
        )

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(template_id)

    r = await conn.fetchrow(
        f"UPDATE document_templates SET {', '.join(parts)}, updated_at=now() WHERE id=${len(params)} RETURNING {_TPL_COLS}",
        *params,
    )
    return _row(r)


# ── POST /templates/{id}/render ───────────────────────────────────────────────

@router.post("/templates/{template_id}/render", response_model=RenderResponse)
async def render_template_endpoint(
    template_id: UUID,
    body: RenderRequest,
    user: CurrentUserDep,
    conn: Db,
) -> RenderResponse:
    tpl_row = await conn.fetchrow(
        "SELECT content FROM document_templates WHERE id=$1 AND is_active=true",
        template_id,
    )
    if tpl_row is None:
        raise ApiError(404, "not_found", "النموذج غير موجود أو غير نشط")

    context: dict = {}
    if body.case_id:
        case_row = await conn.fetchrow(
            "SELECT title, case_number, client_name, court FROM cases WHERE id=$1",
            body.case_id,
        )
        if case_row:
            context["case"] = dict(case_row)

    return render_template(tpl_row["content"], context, body.overrides)
