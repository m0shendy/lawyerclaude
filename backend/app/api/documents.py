"""Documents endpoints (T034): upload + status/chunks reads.

Upload pushes the raw bytes to Supabase Storage, then inserts a `documents`
row born `pending` — the pipeline worker (Phase 4) picks it up asynchronously
and advances it via `app.api.documents_lifecycle`. Chunks are the grounding
source refs for AI outputs. [C-V]

All mutations run on the audited connection (Db) — the DB triggers write the
audit rows. [C-III]
"""

from __future__ import annotations

import json
import logging
import re
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Form, UploadFile
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import assert_case_access
from app.core.security import CurrentUserDep
from app.models import Document, DocumentChunk

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_CONTENT_TYPES = (
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
)

ALLOWED_SOURCE_TYPES = ("text_pdf", "scanned")

_DOCUMENT_COLUMNS = (
    "id, case_id, file_path, file_name, source_type, status, "
    "ocr_confidence, error_detail, uploaded_by, uploaded_at"
)


def _safe_filename(name: str) -> str:
    """Strip path components and reduce to an ASCII-safe Storage object key.

    Supabase Storage object keys must be ASCII (a restricted charset); non-ASCII
    names (e.g. Arabic) are rejected as InvalidKey. We therefore collapse anything
    outside [A-Za-z0-9._-] to '_'. The human-readable original is preserved
    separately in documents.file_name, so display is unaffected.
    """
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return base[-128:] or "document"


def _row_to_document(row) -> Document:
    return Document(**dict(row))


async def _load_document_row(conn, document_id: UUID):
    row = await conn.fetchrow(
        f"SELECT {_DOCUMENT_COLUMNS} FROM documents WHERE id = $1", document_id
    )
    if row is None:
        raise ApiError(404, "not_found", "المستند غير موجود")
    return row


# ── POST /cases/{id}/documents — upload (all 4 roles, case access) ───────────


@router.post("/cases/{case_id}/documents", response_model=Document, status_code=201)
async def upload_document(
    case_id: UUID,
    file: UploadFile,
    user: CurrentUserDep,
    conn: Db,
    source_type: str = Form("scanned"),
) -> Document:
    await assert_case_access(conn, user, case_id)

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError(
            400,
            "unsupported_file_type",
            "نوع الملف غير مدعوم — المسموح: PDF أو صورة (JPEG/PNG/TIFF)",
        )
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ApiError(400, "invalid_source_type", "نوع المصدر غير صالح")

    data = await file.read()
    if not data:
        raise ApiError(400, "empty_file", "الملف فارغ")

    settings = get_settings()
    object_path = f"{case_id}/{uuid4()}_{_safe_filename(file.filename or 'document')}"
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
        logger.exception("Storage upload failed for case %s", case_id)
        raise ApiError(502, "storage_unavailable", "تعذّر الوصول إلى خدمة التخزين")
    if resp.status_code not in (200, 201):
        logger.error("Storage upload rejected (%s): %s", resp.status_code, resp.text[:500])
        raise ApiError(502, "storage_upload_failed", "فشل رفع الملف إلى التخزين")

    row = await conn.fetchrow(
        f"""
        INSERT INTO documents (case_id, file_path, file_name, source_type, status, uploaded_by)
        VALUES ($1, $2, $3, $4, 'pending', $5)
        RETURNING {_DOCUMENT_COLUMNS}
        """,
        case_id,
        object_path,
        file.filename or "document",
        source_type,
        user.id,
    )
    return _row_to_document(row)


# ── GET /documents/{id} — full document (assigned/manager) ───────────────────


@router.get("/documents/{document_id}", response_model=Document)
async def get_document(document_id: UUID, user: CurrentUserDep, conn: Db) -> Document:
    row = await _load_document_row(conn, document_id)
    await assert_case_access(conn, user, row["case_id"])
    return _row_to_document(row)


# ── GET /documents/{id}/status — light status payload ────────────────────────


class DocumentStatusResponse(BaseModel):
    id: UUID
    status: str
    ocr_confidence: float | None = None


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: UUID, user: CurrentUserDep, conn: Db
) -> DocumentStatusResponse:
    row = await _load_document_row(conn, document_id)
    await assert_case_access(conn, user, row["case_id"])
    return DocumentStatusResponse(
        id=row["id"], status=row["status"], ocr_confidence=row["ocr_confidence"]
    )


# ── GET /documents/{id}/chunks — grounding source refs [C-V] ─────────────────


@router.get("/documents/{document_id}/chunks", response_model=list[DocumentChunk])
async def list_document_chunks(
    document_id: UUID, user: CurrentUserDep, conn: Db
) -> list[DocumentChunk]:
    row = await _load_document_row(conn, document_id)
    await assert_case_access(conn, user, row["case_id"])
    chunk_rows = await conn.fetch(
        """
        SELECT id, document_id, chunk_index, chunk_text, page_ref, source_location
        FROM document_chunks
        WHERE document_id = $1
        ORDER BY chunk_index
        """,
        document_id,
    )
    chunks: list[DocumentChunk] = []
    for r in chunk_rows:
        d = dict(r)
        # asyncpg returns jsonb as str unless a codec is registered
        if isinstance(d.get("source_location"), str):
            d["source_location"] = json.loads(d["source_location"])
        chunks.append(DocumentChunk(**d))
    return chunks
