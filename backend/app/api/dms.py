"""Document Management System endpoints (spec 002 US4).

Folders, version chains, pessimistic check-in/out, access levels,
confidentiality, and selective client sharing.

  GET    /cases/{case_id}/folders        — folder tree for a case
  POST   /cases/{case_id}/folders        — create folder
  PATCH  /folders/{id}                   — rename / move folder
  DELETE /folders/{id}                   — delete (cascades to subfolders)

  GET    /documents/{id}/versions        — version chain (newest first)
  POST   /documents/{id}/checkout        — acquire exclusive lock (409 if held)
  DELETE /documents/{id}/checkout        — release without a new version
  POST   /documents/{id}/checkin         — upload new version + release lock

  PATCH  /documents/{id}/access          — access level / confidentiality
  POST   /documents/{id}/share           — share with a client contact
  DELETE /documents/{id}/share/{contact_id} — unshare

All mutations run on the audited connection — DB triggers write the audit
rows [C-III]. Confidential documents are blocked from sharing at both the
API and DB-trigger layers.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel

from app.api.documents import _safe_filename
from app.core.config import get_settings
from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, PARALEGAL, assert_case_access, require_roles
from app.core.security import CurrentUser, CurrentUserDep

logger = logging.getLogger(__name__)

router = APIRouter()

AccessLevel = Literal["public", "team", "restricted"]

_FOLDER_COLS = "id, case_id, name, parent_folder_id, created_by, created_at"
_VERSION_COLS = (
    "id, document_id, version_number, file_path, file_name, "
    "prev_version_id, uploaded_by, uploaded_at, note"
)


# ── models ────────────────────────────────────────────────────────────────────


class Folder(BaseModel):
    id: UUID
    case_id: UUID
    name: str
    parent_folder_id: UUID | None = None
    created_by: UUID | None = None
    created_at: datetime


class FolderCreate(BaseModel):
    name: str
    parent_folder_id: UUID | None = None


class FolderUpdate(BaseModel):
    name: str | None = None
    parent_folder_id: UUID | None = None


class DocumentVersion(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    file_path: str
    file_name: str
    prev_version_id: UUID | None = None
    uploaded_by: UUID | None = None
    uploaded_at: datetime
    note: str | None = None


class CheckoutInfo(BaseModel):
    document_id: UUID
    checked_out_by: UUID
    checked_out_by_name: str | None = None
    checked_out_at: datetime


class AccessUpdate(BaseModel):
    access_level: AccessLevel | None = None
    is_confidential: bool | None = None


class ShareRequest(BaseModel):
    contact_id: UUID


# ── helpers ───────────────────────────────────────────────────────────────────


async def _doc_case_id(conn, document_id: UUID) -> UUID:
    case_id = await conn.fetchval(
        "SELECT case_id FROM documents WHERE id = $1", document_id
    )
    if case_id is None:
        raise ApiError(404, "not_found", "المستند غير موجود")
    return case_id


# ── folders ───────────────────────────────────────────────────────────────────


@router.get("/cases/{case_id}/folders", response_model=list[Folder])
async def list_folders(case_id: UUID, user: CurrentUserDep, conn: Db) -> list[Folder]:
    await assert_case_access(conn, user, case_id)
    rows = await conn.fetch(
        f"SELECT {_FOLDER_COLS} FROM document_folders WHERE case_id = $1 ORDER BY name",
        case_id,
    )
    return [Folder(**dict(r)) for r in rows]


@router.post("/cases/{case_id}/folders", response_model=Folder, status_code=201)
async def create_folder(
    case_id: UUID,
    body: FolderCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL))],
) -> Folder:
    await assert_case_access(conn, user, case_id)
    if not body.name.strip():
        raise ApiError(400, "validation_error", "اسم المجلد مطلوب")
    if body.parent_folder_id is not None:
        parent_case = await conn.fetchval(
            "SELECT case_id FROM document_folders WHERE id = $1", body.parent_folder_id
        )
        if parent_case != case_id:
            raise ApiError(400, "invalid", "المجلد الأصل لا ينتمي لنفس القضية")
    try:
        row = await conn.fetchrow(
            f"""
            INSERT INTO document_folders (case_id, name, parent_folder_id, created_by)
            VALUES ($1, $2, $3, $4)
            RETURNING {_FOLDER_COLS}
            """,
            case_id, body.name.strip(), body.parent_folder_id, user.id,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise ApiError(409, "conflict", "مجلد بهذا الاسم موجود بالفعل") from exc
        raise
    return Folder(**dict(row))


@router.patch("/folders/{folder_id}", response_model=Folder)
async def update_folder(
    folder_id: UUID,
    body: FolderUpdate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL))],
) -> Folder:
    existing = await conn.fetchrow(
        f"SELECT {_FOLDER_COLS} FROM document_folders WHERE id = $1", folder_id
    )
    if existing is None:
        raise ApiError(404, "not_found", "المجلد غير موجود")
    await assert_case_access(conn, user, existing["case_id"])

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return Folder(**dict(existing))
    if updates.get("parent_folder_id") == folder_id:
        raise ApiError(400, "invalid", "لا يمكن نقل المجلد إلى نفسه")

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(folder_id)
    row = await conn.fetchrow(
        f"""
        UPDATE document_folders SET {", ".join(parts)}
        WHERE id = ${len(params)}
        RETURNING {_FOLDER_COLS}
        """,
        *params,
    )
    return Folder(**dict(row))


@router.delete("/folders/{folder_id}", status_code=200)
async def delete_folder(
    folder_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> dict:
    case_id = await conn.fetchval(
        "SELECT case_id FROM document_folders WHERE id = $1", folder_id
    )
    if case_id is None:
        raise ApiError(404, "not_found", "المجلد غير موجود")
    await assert_case_access(conn, user, case_id)
    deleted = await conn.fetchval(
        "DELETE FROM document_folders WHERE id = $1 RETURNING id", folder_id
    )
    return {"status": "deleted", "id": str(deleted)}


# ── versions ──────────────────────────────────────────────────────────────────


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersion])
async def list_versions(
    document_id: UUID, user: CurrentUserDep, conn: Db
) -> list[DocumentVersion]:
    case_id = await _doc_case_id(conn, document_id)
    await assert_case_access(conn, user, case_id)
    rows = await conn.fetch(
        f"""
        SELECT {_VERSION_COLS} FROM document_versions
        WHERE document_id = $1 ORDER BY version_number DESC
        """,
        document_id,
    )
    return [DocumentVersion(**dict(r)) for r in rows]


# ── check-out / check-in (pessimistic lock, R3) ──────────────────────────────


@router.get("/documents/{document_id}/checkout", response_model=CheckoutInfo | None)
async def get_checkout(
    document_id: UUID, user: CurrentUserDep, conn: Db
) -> CheckoutInfo | None:
    case_id = await _doc_case_id(conn, document_id)
    await assert_case_access(conn, user, case_id)
    row = await conn.fetchrow(
        """
        SELECT c.document_id, c.checked_out_by, c.checked_out_at, u.full_name
        FROM document_checkouts c LEFT JOIN users u ON u.id = c.checked_out_by
        WHERE c.document_id = $1
        """,
        document_id,
    )
    if row is None:
        return None
    return CheckoutInfo(
        document_id=row["document_id"],
        checked_out_by=row["checked_out_by"],
        checked_out_by_name=row["full_name"],
        checked_out_at=row["checked_out_at"],
    )


@router.post("/documents/{document_id}/checkout", response_model=CheckoutInfo, status_code=201)
async def checkout_document(
    document_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL))],
) -> CheckoutInfo:
    case_id = await _doc_case_id(conn, document_id)
    await assert_case_access(conn, user, case_id)

    # Single INSERT; the unique constraint on document_id is the lock.
    row = await conn.fetchrow(
        """
        INSERT INTO document_checkouts (document_id, checked_out_by)
        VALUES ($1, $2)
        ON CONFLICT (document_id) DO NOTHING
        RETURNING document_id, checked_out_by, checked_out_at
        """,
        document_id, user.id,
    )
    if row is None:
        holder = await conn.fetchrow(
            """
            SELECT u.full_name FROM document_checkouts c
            LEFT JOIN users u ON u.id = c.checked_out_by
            WHERE c.document_id = $1
            """,
            document_id,
        )
        name = holder["full_name"] if holder else "مستخدم آخر"
        raise ApiError(
            409, "document_checked_out",
            f"المستند محجوز للتعديل بواسطة {name}",
        )
    return CheckoutInfo(
        document_id=row["document_id"],
        checked_out_by=row["checked_out_by"],
        checked_out_by_name=user.full_name,
        checked_out_at=row["checked_out_at"],
    )


@router.delete("/documents/{document_id}/checkout", status_code=200)
async def release_checkout(
    document_id: UUID, user: CurrentUserDep, conn: Db
) -> dict:
    case_id = await _doc_case_id(conn, document_id)
    await assert_case_access(conn, user, case_id)
    holder = await conn.fetchval(
        "SELECT checked_out_by FROM document_checkouts WHERE document_id = $1",
        document_id,
    )
    if holder is None:
        raise ApiError(404, "not_found", "المستند غير محجوز")
    if holder != user.id and user.role != MANAGER:
        raise ApiError(403, "forbidden", "الحجز يخص مستخدمًا آخر")
    await conn.execute(
        "DELETE FROM document_checkouts WHERE document_id = $1", document_id
    )
    return {"status": "released", "document_id": str(document_id)}


@router.post("/documents/{document_id}/checkin", response_model=DocumentVersion, status_code=201)
async def checkin_document(
    document_id: UUID,
    file: UploadFile,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL))],
) -> DocumentVersion:
    """Upload a new version, advance the chain, and release the lock. [C-III]"""
    case_id = await _doc_case_id(conn, document_id)
    await assert_case_access(conn, user, case_id)

    holder = await conn.fetchval(
        "SELECT checked_out_by FROM document_checkouts WHERE document_id = $1",
        document_id,
    )
    if holder is None:
        raise ApiError(409, "not_checked_out", "يجب حجز المستند قبل إيداع نسخة جديدة")
    if holder != user.id and user.role != MANAGER:
        raise ApiError(403, "forbidden", "الحجز يخص مستخدمًا آخر")

    data = await file.read()
    if not data:
        raise ApiError(400, "empty_file", "الملف فارغ")

    prev = await conn.fetchrow(
        """
        SELECT id, version_number FROM document_versions
        WHERE document_id = $1 ORDER BY version_number DESC LIMIT 1
        """,
        document_id,
    )
    next_version = (prev["version_number"] + 1) if prev else 2  # original upload = v1

    settings = get_settings()
    file_name = file.filename or "document"
    object_path = (
        f"{case_id}/{document_id}/v{next_version}_{uuid4().hex[:8]}_"
        f"{_safe_filename(file_name)}"
    )
    content_type = (file.content_type or "application/octet-stream").split(";")[0]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.supabase_url}/storage/v1/object/"
                f"{settings.storage_bucket}/{object_path}",
                headers={
                    "authorization": f"Bearer {settings.supabase_service_key}",
                    "apikey": settings.supabase_service_key,
                    "content-type": content_type,
                },
                content=data,
            )
    except httpx.HTTPError:
        logger.exception("Storage upload failed for checkin %s", document_id)
        raise ApiError(502, "storage_unavailable", "تعذّر الوصول إلى خدمة التخزين")
    if resp.status_code not in (200, 201):
        logger.error("Storage rejected checkin (%s): %s", resp.status_code, resp.text[:500])
        raise ApiError(502, "storage_upload_failed", "فشل رفع الملف إلى التخزين")

    async with conn.transaction():
        # Backfill v1 from the original upload if the chain is empty.
        if prev is None:
            orig = await conn.fetchrow(
                "SELECT file_path, file_name, uploaded_by, uploaded_at "
                "FROM documents WHERE id = $1",
                document_id,
            )
            v1 = await conn.fetchrow(
                f"""
                INSERT INTO document_versions
                    (document_id, version_number, file_path, file_name,
                     uploaded_by, uploaded_at, note)
                VALUES ($1, 1, $2, $3, $4, $5, 'النسخة الأصلية')
                RETURNING {_VERSION_COLS}
                """,
                document_id, orig["file_path"], orig["file_name"],
                orig["uploaded_by"], orig["uploaded_at"],
            )
            prev_id = v1["id"]
        else:
            prev_id = prev["id"]

        row = await conn.fetchrow(
            f"""
            INSERT INTO document_versions
                (document_id, version_number, file_path, file_name,
                 prev_version_id, uploaded_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING {_VERSION_COLS}
            """,
            document_id, next_version, object_path, file_name, prev_id, user.id,
        )
        # documents row always points at the latest version.
        await conn.execute(
            "UPDATE documents SET file_path = $1, file_name = $2, updated_at = now() "
            "WHERE id = $3",
            object_path, file_name, document_id,
        )
        # Release the lock (audit trigger records the delete) [C-III].
        await conn.execute(
            "DELETE FROM document_checkouts WHERE document_id = $1", document_id
        )
    return DocumentVersion(**dict(row))


# ── access level / confidentiality / sharing ─────────────────────────────────


@router.patch("/documents/{document_id}/access", status_code=200)
async def update_access(
    document_id: UUID,
    body: AccessUpdate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> dict:
    case_id = await _doc_case_id(conn, document_id)
    await assert_case_access(conn, user, case_id)
    updates = body.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise ApiError(400, "validation_error", "لا توجد تعديلات")

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        params.append(value)
        parts.append(f"{field} = ${len(params)}")
    params.append(document_id)
    try:
        await conn.execute(
            f"UPDATE documents SET {', '.join(parts)}, updated_at = now() "
            f"WHERE id = ${len(params)}",
            *params,
        )
    except Exception as exc:
        if "active shares" in str(exc):
            raise ApiError(
                409, "has_active_shares",
                "المستند مُشارك مع عملاء — ألغِ المشاركة قبل جعله سريًا",
            ) from exc
        raise
    return {"status": "updated", "id": str(document_id), **updates}


@router.post("/documents/{document_id}/share", status_code=201)
async def share_document(
    document_id: UUID,
    body: ShareRequest,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> dict:
    case_id = await _doc_case_id(conn, document_id)
    await assert_case_access(conn, user, case_id)

    confidential = await conn.fetchval(
        "SELECT is_confidential FROM documents WHERE id = $1", document_id
    )
    if confidential:
        raise ApiError(403, "confidential", "لا يمكن مشاركة مستند سري")

    contact = await conn.fetchval(
        "SELECT id FROM contacts WHERE id = $1 AND is_active", body.contact_id
    )
    if contact is None:
        raise ApiError(404, "not_found", "جهة الاتصال غير موجودة")

    row = await conn.fetchrow(
        """
        INSERT INTO document_sharing (document_id, contact_id, shared_by)
        VALUES ($1, $2, $3)
        ON CONFLICT (document_id, contact_id) DO NOTHING
        RETURNING id
        """,
        document_id, body.contact_id, user.id,
    )
    if row is None:
        raise ApiError(409, "conflict", "المستند مُشارك بالفعل مع هذا العميل")
    return {"status": "shared", "id": str(row["id"])}


@router.delete("/documents/{document_id}/share/{contact_id}", status_code=200)
async def unshare_document(
    document_id: UUID,
    contact_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> dict:
    case_id = await _doc_case_id(conn, document_id)
    await assert_case_access(conn, user, case_id)
    deleted = await conn.fetchval(
        "DELETE FROM document_sharing WHERE document_id = $1 AND contact_id = $2 "
        "RETURNING id",
        document_id, contact_id,
    )
    if deleted is None:
        raise ApiError(404, "not_found", "المشاركة غير موجودة")
    return {"status": "unshared", "id": str(deleted)}


# ── document templates (T030) ─────────────────────────────────────────────────
#
# Two-pass generation:
#   Pass 1: Mustache-style {{variable}} substitution from matter/client data.
#   Pass 2: LiteLLM dispatch for {{AI: …}} instruction blocks.
# Every generated output is born draft_unreviewed [C-II].
# Missing variables are marked [MISSING: var_name] — never left blank [C-II].


import re as _re

_TEMPLATE_COLS = (
    "id, name, name_ar, category, content_template, variables_schema, "
    "created_by, created_at"
)


class TemplateBase(BaseModel):
    name: str
    name_ar: str
    category: str | None = None  # contract, submission, engagement_letter, letter, other
    content_template: str
    variables_schema: list[dict] = []


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    category: str | None = None
    content_template: str | None = None
    variables_schema: list[dict] | None = None


class TemplateResponse(TemplateBase):
    id: UUID
    created_by: UUID | None = None
    created_at: datetime


class GenerateFromTemplateRequest(BaseModel):
    case_id: UUID
    context: str | None = None


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    user: CurrentUserDep,
    conn: Db,
    category: str | None = None,
) -> list[TemplateResponse]:
    if category:
        rows = await conn.fetch(
            f"SELECT {_TEMPLATE_COLS} FROM document_templates WHERE category = $1 ORDER BY name_ar",
            category,
        )
    else:
        rows = await conn.fetch(
            f"SELECT {_TEMPLATE_COLS} FROM document_templates ORDER BY name_ar"
        )
    return [TemplateResponse(**dict(r)) for r in rows]


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    body: TemplateCreate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> TemplateResponse:
    import json as _json
    row = await conn.fetchrow(
        f"""
        INSERT INTO document_templates
            (name, name_ar, category, content_template, variables_schema, created_by)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6)
        RETURNING {_TEMPLATE_COLS}
        """,
        body.name, body.name_ar, body.category,
        body.content_template, _json.dumps(body.variables_schema), user.id,
    )
    return TemplateResponse(**dict(row))


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: UUID, user: CurrentUserDep, conn: Db) -> TemplateResponse:
    row = await conn.fetchrow(
        f"SELECT {_TEMPLATE_COLS} FROM document_templates WHERE id = $1", template_id
    )
    if row is None:
        raise ApiError(404, "not_found", "النموذج غير موجود")
    return TemplateResponse(**dict(row))


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: UUID,
    body: TemplateUpdate,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> TemplateResponse:
    import json as _json
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            f"SELECT {_TEMPLATE_COLS} FROM document_templates WHERE id = $1", template_id
        )
        if row is None:
            raise ApiError(404, "not_found", "النموذج غير موجود")
        return TemplateResponse(**dict(row))

    params: list = []
    parts: list[str] = []
    for field, value in updates.items():
        if field == "variables_schema":
            value = _json.dumps(value)
            parts.append(f"{field} = ${len(params)+1}::jsonb")
        else:
            parts.append(f"{field} = ${len(params)+1}")
        params.append(value)
    params.append(template_id)
    row = await conn.fetchrow(
        f"""
        UPDATE document_templates SET {', '.join(parts)}
        WHERE id = ${len(params)}
        RETURNING {_TEMPLATE_COLS}
        """,
        *params,
    )
    if row is None:
        raise ApiError(404, "not_found", "النموذج غير موجود")
    return TemplateResponse(**dict(row))


@router.delete("/templates/{template_id}", status_code=200)
async def delete_template(
    template_id: UUID,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> dict:
    deleted = await conn.fetchval(
        "DELETE FROM document_templates WHERE id = $1 RETURNING id", template_id
    )
    if deleted is None:
        raise ApiError(404, "not_found", "النموذج غير موجود")
    return {"status": "deleted", "id": str(deleted)}


@router.post("/templates/{template_id}/generate", status_code=201)
async def generate_from_template(
    template_id: UUID,
    body: GenerateFromTemplateRequest,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER))],
) -> dict:
    """Two-pass template generation → ai_outputs row (draft_unreviewed) [C-II].

    Pass 1: Mustache substitution of {{var}} from matter/client context.
    Pass 2: LiteLLM dispatch for {{AI: <instruction>}} blocks.
    Missing variables → [MISSING: var_name] placeholders, never left blank.
    """
    import json as _json
    from app.llm.providers import dispatch as llm_dispatch, LLMProviderError

    tpl_row = await conn.fetchrow(
        f"SELECT {_TEMPLATE_COLS} FROM document_templates WHERE id = $1", template_id
    )
    if tpl_row is None:
        raise ApiError(404, "not_found", "النموذج غير موجود")

    # Fetch matter context for variable substitution
    case_row = await conn.fetchrow(
        """
        SELECT c.title, c.case_number, c.practice_area, c.stage,
               con.name AS client_name, con.phone AS client_phone, con.email AS client_email
        FROM cases c
        LEFT JOIN contacts con ON con.id = c.client_contact_id
        WHERE c.id = $1
        """,
        body.case_id,
    )
    if case_row is None:
        raise ApiError(404, "not_found", "القضية غير موجودة")

    ctx: dict[str, str] = {
        "case_title": case_row["title"] or "",
        "case_number": case_row["case_number"] or "",
        "practice_area": case_row["practice_area"] or "",
        "client_name": case_row["client_name"] or "",
        "client_phone": case_row["client_phone"] or "",
        "client_email": case_row["client_email"] or "",
        "context": body.context or "",
    }

    # Pass 1: substitute {{variable}} placeholders
    content = tpl_row["content_template"]

    def _substitute(match: "_re.Match[str]") -> str:
        var = match.group(1).strip()
        val = ctx.get(var)
        if val:
            return val
        return f"[MISSING: {var}]"

    content = _re.sub(r"\{\{(?!AI:)([^}]+)\}\}", _substitute, content)

    # Pass 2: replace {{AI: <instruction>}} blocks via LLM [C-II]
    ai_blocks = list(_re.finditer(r"\{\{AI:\s*([^}]+)\}\}", content))
    if ai_blocks:
        firm_row = await conn.fetchrow(
            "SELECT llm_provider_config, llm_api_key FROM firm_settings LIMIT 1"
        )
        if firm_row is None:
            raise ApiError(503, "no_settings", "لم يتم تهيئة إعدادات الشركة")

        for match in reversed(ai_blocks):
            instruction = match.group(1).strip()
            prompt = (
                f"أنت مساعد قانوني. أكمل الجزء التالي من المستند وفقًا للتعليمات:\n"
                f"التعليمات: {instruction}\n"
                f"سياق القضية: {body.context or 'غير محدد'}\n"
                f"العميل: {ctx['client_name']}\n"
                f"رقم القضية: {ctx['case_number']}\n"
                "اكتب النص فقط دون تعليقات."
            )
            try:
                ai_text = await llm_dispatch(prompt, [], firm_row)
            except LLMProviderError as exc:
                logger.warning("LLM failed for AI block in template generate: %s", exc)
                ai_text = f"[MISSING: AI block — {instruction}]"
            content = content[:match.start()] + ai_text + content[match.end():]

    # Fetch firm settings for review (needed to build output)
    output_row = await conn.fetchrow(
        f"""
        INSERT INTO ai_outputs
            (case_id, type, content, review_state, source_links, created_by, template_id)
        VALUES ($1, 'doc_draft', $2::jsonb, 'draft_unreviewed', '[]'::jsonb, $3, $4)
        RETURNING id, type, review_state, created_at
        """,
        body.case_id,
        _json.dumps({"draft": content, "template_name": tpl_row["name_ar"]}),
        user.id,
        template_id,
    )
    return {
        "output_id": str(output_row["id"]),
        "review_state": output_row["review_state"],
        "type": output_row["type"],
        "created_at": output_row["created_at"].isoformat(),
        "preview": content[:500] + ("…" if len(content) > 500 else ""),
    }
