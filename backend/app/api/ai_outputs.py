"""AI outputs API (T055–T059). [C-II][C-V][C-VI][C-VII]

Endpoints
---------
  GET  /ai-outputs                     — list / review queue (T055)
  GET  /ai-outputs/{id}                — detail with content + source_links (T055)
  POST /documents/{id}/summarize       — summarize + extract (T056, T057)
  POST /ai-outputs/{id}/approve        — approve gate (T058) — lawyer/manager only
  POST /ai-outputs/{id}/export         — export gate (T059) — 403 if not approved

Constitution invariants encoded in this file
--------------------------------------------
[C-II] Every output is born ``draft_unreviewed``; export/send blocked until approved.
       Approval cannot be reversed; content is immutable after approval.
[C-III] Approval is a high-value audit event recorded with who/when/version.
[C-V]  Every output stores ``source_links`` → chunk_id/document_id/page_ref.
[C-VI] AI marking ("draft_unreviewed") is surfaced by the API payload; the UI
       renders the banner.
[C-VII] ``low_confidence_flag`` is propagated from the source document; the UI
        shows the heightened warning.

Approval authority (FR-018, clarified 2026-06-05)
--------------------------------------------------
Only the lawyer *assigned* to the case, or any partner_manager, may approve.
Paralegals and secretaries → 403.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, assert_case_access, is_assigned_to_case, require_roles
from app.core.security import CurrentUser, CurrentUserDep
from app.llm.generate import LlmError, SUMMARIZE_INSTRUCTION, build_prompt, generate
from app.models import AiOutput, AiOutputType, ReviewState, SourceLink
from app.retriever.retrieve import RetrievedChunk, retrieve

logger = logging.getLogger(__name__)

router = APIRouter()

_OUTPUT_COLUMNS = (
    "id, document_id, case_id, type, content, source_links, review_state, "
    "low_confidence_flag, generated_by_model, created_at, "
    "approved_by, approved_at, approved_version"
)

# Approval is restricted to assigned lawyers + managers.  [FR-018]
APPROVAL_ROLES = {MANAGER, LAWYER}


def _row_to_output(row) -> AiOutput:
    d = dict(row)
    # asyncpg returns jsonb as str or dict depending on codec registration.
    for field in ("content", "source_links"):
        if isinstance(d.get(field), str):
            d[field] = json.loads(d[field])
    if not isinstance(d.get("source_links"), list):
        d["source_links"] = []
    return AiOutput(**d)


async def _get_output_or_404(conn, output_id: UUID) -> AiOutput:
    row = await conn.fetchrow(
        f"SELECT {_OUTPUT_COLUMNS} FROM ai_outputs WHERE id = $1", output_id
    )
    if row is None:
        raise ApiError(404, "not_found", "مخرج الذكاء الاصطناعي غير موجود")
    return _row_to_output(row)


async def _case_id_for_output(conn, output: AiOutput) -> UUID:
    """Resolve the case_id for access checking (via document if needed)."""
    if output.case_id is not None:
        return output.case_id
    case_id = await conn.fetchval(
        "SELECT case_id FROM documents WHERE id = $1", output.document_id
    )
    if case_id is None:
        raise ApiError(404, "not_found", "القضية المرتبطة بالمخرج غير موجودة")
    return case_id


# ── GET /ai-outputs — list + review queue ─────────────────────────────────────


class AiOutputListItem(BaseModel):
    id: UUID
    document_id: UUID | None
    case_id: UUID | None
    type: AiOutputType
    review_state: ReviewState
    low_confidence_flag: bool
    created_at: datetime


@router.get("/ai-outputs", response_model=list[AiOutputListItem])
async def list_ai_outputs(
    user: CurrentUserDep,
    conn: Db,
    state: ReviewState | None = Query(default=None),
    case_id: UUID | None = Query(default=None),
) -> list[AiOutputListItem]:
    """List AI outputs visible to the caller (scoped by RBAC + case access)."""
    conditions = []
    params: list[Any] = []

    if state is not None:
        params.append(state)
        conditions.append(f"o.review_state = ${len(params)}")

    if user.role != MANAGER:
        # Non-managers see only outputs for their assigned cases.
        params.append(user.id)
        conditions.append(
            f"""
            (
                (o.case_id IS NOT NULL AND EXISTS (
                    SELECT 1 FROM case_assignments
                    WHERE case_id = o.case_id AND user_id = ${len(params)}
                ))
                OR
                (o.document_id IS NOT NULL AND EXISTS (
                    SELECT 1 FROM case_assignments ca
                    JOIN documents d ON d.case_id = ca.case_id
                    WHERE d.id = o.document_id AND ca.user_id = ${len(params)}
                ))
            )
            """
        )
    elif case_id is not None:
        params.append(case_id)
        conditions.append(
            f"(o.case_id = ${len(params)} OR o.document_id IN "
            f"(SELECT id FROM documents WHERE case_id = ${len(params)}))"
        )

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = await conn.fetch(
        f"""
        SELECT o.id, o.document_id, o.case_id, o.type, o.review_state,
               o.low_confidence_flag, o.created_at
        FROM ai_outputs o
        {where}
        ORDER BY o.created_at DESC
        LIMIT 200
        """,
        *params,
    )
    return [AiOutputListItem(**dict(r)) for r in rows]


# ── GET /ai-outputs/{id} — detail ────────────────────────────────────────────


@router.get("/ai-outputs/{output_id}", response_model=AiOutput)
async def get_ai_output(
    output_id: UUID, user: CurrentUserDep, conn: Db
) -> AiOutput:
    """Return full AI output with content, source_links, and review state."""
    output = await _get_output_or_404(conn, output_id)
    case_id = await _case_id_for_output(conn, output)
    await assert_case_access(conn, user, case_id)
    return output


# ── POST /documents/{id}/summarize — summarize + extract (T056, T057) ─────────


class SummarizeResponse(BaseModel):
    summary_output: AiOutput
    extraction_output: AiOutput


@router.post(
    "/documents/{document_id}/summarize",
    response_model=SummarizeResponse,
    status_code=201,
)
async def summarize_document(
    document_id: UUID,
    user: CurrentUserDep,
    conn: Db,
) -> SummarizeResponse:
    """Generate a summary + key-point extraction for a document.

    Both outputs are born ``draft_unreviewed``, AI-marked, with source_links
    grounding every claim.  [C-II][C-V][C-VI][C-VII]

    Only allowed on ``ready`` or ``low_confidence`` documents (``failed`` and
    ``pending``/``processing`` are rejected).
    """
    # Load document and verify access.
    doc_row = await conn.fetchrow(
        "SELECT id, case_id, status, ocr_confidence FROM documents WHERE id = $1",
        document_id,
    )
    if doc_row is None:
        raise ApiError(404, "not_found", "المستند غير موجود")
    await assert_case_access(conn, user, doc_row["case_id"])

    if doc_row["status"] not in ("ready", "low_confidence"):
        raise ApiError(
            400,
            "invalid_state",
            f"لا يمكن تلخيص مستند بالحالة «{doc_row['status']}» — "
            "انتظر حتى تكتمل المعالجة",
        )

    low_confidence_flag = doc_row["status"] == "low_confidence"  # [C-VII]

    # Read embedding config + API key from firm_settings.
    firm = await conn.fetchrow(
        "SELECT llm_api_key, embedding_config FROM firm_settings LIMIT 1"
    )
    if firm is None:
        raise ApiError(500, "config_error", "إعدادات المكتب غير موجودة")

    api_key: str = firm["llm_api_key"] or ""
    emb_cfg = firm["embedding_config"]
    if isinstance(emb_cfg, str):
        emb_cfg = json.loads(emb_cfg)

    # Retrieve relevant chunks from the document.  [C-V]
    chunks = await retrieve(
        query=SUMMARIZE_INSTRUCTION,
        conn=conn,
        api_key=api_key,
        embedding_config=emb_cfg,
        document_id=document_id,
        include_shared=False,  # summarization is purely document-scoped
    )

    if not chunks:
        raise ApiError(
            422,
            "no_chunks",
            "لا توجد مقاطع قابلة للاسترجاع في هذا المستند — "
            "تأكد من اكتمال المعالجة",
        )

    # Build and send prompt.
    context_texts = [c.chunk_text for c in chunks]
    prompt = build_prompt(SUMMARIZE_INSTRUCTION, context_texts)

    try:
        llm_model = (emb_cfg or {}).get("llm_model", "models/gemini-2.0-flash")
        raw_text = await generate(prompt, api_key=api_key, model=llm_model)
    except LlmError as exc:
        raise ApiError(502, "llm_error", str(exc)) from exc

    # Parse the LLM response.  Extract the JSON block if present.
    content_dict = _parse_llm_response(raw_text, context_texts)

    # Build source_links from retrieved chunks.  [C-V]
    source_links = _build_source_links(chunks)

    # Persist both outputs as draft_unreviewed.  [C-II]
    summary_output = await _create_ai_output(
        conn,
        document_id=document_id,
        case_id=doc_row["case_id"],
        output_type="summary",
        content=content_dict,
        source_links=source_links,
        low_confidence_flag=low_confidence_flag,
        model=llm_model,
    )
    extraction_output = await _create_ai_output(
        conn,
        document_id=document_id,
        case_id=doc_row["case_id"],
        output_type="extraction",
        content=_extract_structured(content_dict),
        source_links=source_links,
        low_confidence_flag=low_confidence_flag,
        model=llm_model,
    )

    return SummarizeResponse(
        summary_output=summary_output,
        extraction_output=extraction_output,
    )


# ── POST /ai-outputs/{id}/approve — review gate approval (T058) ──────────────


class ApproveRequest(BaseModel):
    version: int = 1


@router.post("/ai-outputs/{output_id}/approve", response_model=AiOutput)
async def approve_ai_output(
    output_id: UUID,
    body: ApproveRequest,
    user: CurrentUserDep,
    conn: Db,
) -> AiOutput:
    """Approve a draft_unreviewed output.

    Only the *assigned lawyer* (via case_assignments) or a *partner_manager*
    may approve.  Paralegals and secretaries are denied (403).  [FR-018][C-II]
    """
    if user.role not in APPROVAL_ROLES:
        raise ApiError(
            403,
            "forbidden",
            "صلاحيات المراجعة والاعتماد مقتصرة على المحامي المكلَّف بالقضية "
            "أو الشريك / المدير",
        )

    output = await _get_output_or_404(conn, output_id)
    case_id = await _case_id_for_output(conn, output)
    await assert_case_access(conn, user, case_id)

    # Lawyers must be assigned to the case; managers can always approve.
    if user.role == LAWYER:
        if not await is_assigned_to_case(conn, user.id, case_id):
            raise ApiError(
                403,
                "forbidden",
                "يجب أن تكون مُكلَّفاً بالقضية لتتمكن من اعتماد هذا المخرج",
            )

    if output.review_state == "approved":
        raise ApiError(
            409,
            "invalid_state",
            "تم اعتماد هذا المخرج مسبقاً",
        )

    now = datetime.now(timezone.utc)

    row = await conn.fetchrow(
        f"""
        UPDATE ai_outputs
        SET review_state = 'approved',
            approved_by = $2,
            approved_at = $3,
            approved_version = $4
        WHERE id = $1
        RETURNING {_OUTPUT_COLUMNS}
        """,
        output_id,
        user.id,
        now,
        body.version,
    )
    if row is None:
        raise ApiError(404, "not_found", "مخرج الذكاء الاصطناعي غير موجود")

    logger.info(
        "ai_outputs: approved output=%s by user=%s (role=%s) version=%d",
        output_id, user.id, user.role, body.version,
    )
    return _row_to_output(row)


# ── POST /ai-outputs/{id}/export — export gate (T059) ────────────────────────


class ExportResponse(BaseModel):
    id: UUID
    review_state: ReviewState
    content: dict[str, Any]
    source_links: list[SourceLink]
    approved_by: UUID | None
    approved_at: datetime | None
    approved_version: int | None


@router.post("/ai-outputs/{output_id}/export", response_model=ExportResponse)
async def export_ai_output(
    output_id: UUID, user: CurrentUserDep, conn: Db
) -> ExportResponse:
    """Return output content for export/print/attach/send.

    REJECTS with 403 if not approved.  This is the ONLY code path for
    official-use output — the DB view ``ai_outputs_exportable`` provides
    defense in depth at the DB layer.  [C-II]
    """
    # Read from the export-safe view (approved rows only).  [C-II]
    row = await conn.fetchrow(
        f"""
        SELECT {_OUTPUT_COLUMNS}
        FROM ai_outputs_exportable
        WHERE id = $1
        """,
        output_id,
    )
    if row is None:
        # Either not found OR not yet approved — return the same 403 in both
        # cases so the caller cannot probe for existence of unapproved outputs.
        raise ApiError(
            403,
            "review_gate_blocked",
            "هذا المخرج لم يُعتمد بعد — التصدير / الإرسال الرسمي غير مسموح "
            "حتى يتم «تمت المراجعة والاعتماد» من المحامي المكلَّف أو الشريك",
        )

    output = _row_to_output(row)
    case_id = await _case_id_for_output(conn, output)
    await assert_case_access(conn, user, case_id)

    return ExportResponse(
        id=output.id,
        review_state=output.review_state,
        content=output.content,
        source_links=output.source_links,
        approved_by=output.approved_by,
        approved_at=output.approved_at,
        approved_version=output.approved_version,
    )


# ── internal helpers ──────────────────────────────────────────────────────────


async def _create_ai_output(
    conn,
    *,
    document_id: UUID | None,
    case_id: UUID | None,
    output_type: AiOutputType,
    content: dict[str, Any],
    source_links: list[dict],
    low_confidence_flag: bool,
    model: str,
) -> AiOutput:
    """Insert a new ai_output row in draft_unreviewed state."""
    row = await conn.fetchrow(
        f"""
        INSERT INTO ai_outputs
            (document_id, case_id, type, content, source_links,
             review_state, low_confidence_flag, generated_by_model)
        VALUES ($1, $2, $3, $4, $5, 'draft_unreviewed', $6, $7)
        RETURNING {_OUTPUT_COLUMNS}
        """,
        document_id,
        case_id,
        output_type,
        json.dumps(content, ensure_ascii=False),
        json.dumps(source_links, ensure_ascii=False),
        low_confidence_flag,
        model,
    )
    return _row_to_output(row)


def _build_source_links(chunks: list[RetrievedChunk]) -> list[dict]:
    """Convert retrieved chunks to the source_links JSON format."""
    return [
        {
            "chunk_id": str(c.chunk_id),
            "document_id": str(c.document_id),
            "page_ref": c.page_ref,
        }
        for c in chunks
    ]


def _parse_llm_response(raw_text: str, context_texts: list[str]) -> dict[str, Any]:
    """Try to extract JSON from the LLM response; fall back to raw text."""
    # Look for a JSON block in the response.
    import re
    json_match = re.search(r"\{[\s\S]*\}", raw_text)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            parsed["raw_text"] = raw_text
            parsed["context_count"] = len(context_texts)
            return parsed
        except json.JSONDecodeError:
            pass
    return {
        "raw_text": raw_text,
        "context_count": len(context_texts),
    }


def _extract_structured(content_dict: dict[str, Any]) -> dict[str, Any]:
    """Return just the structured extraction fields."""
    keys = ["الأطراف", "التواريخ", "المطالبات", "المبالغ", "النقاط_الرئيسية"]
    extracted = {k: content_dict.get(k, []) for k in keys}
    extracted["raw_text"] = content_dict.get("raw_text", "")
    extracted["context_count"] = content_dict.get("context_count", 0)
    return extracted
