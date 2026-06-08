"""AI document features (spec 002 US1/US12/US13): draft, letter pack, timeline.

  POST /ai/draft-document — AI-drafted contract / submission / engagement letter
  POST /ai/letter-pack    — template merge (deterministic) + AI contextual blocks
  POST /ai/case-timeline  — chronological event extraction for a matter

Pipeline identical to spec 001: Retriever (Component A) → multi-provider LLM
dispatch (Component B) → ``ai_outputs`` row born ``draft_unreviewed`` with
``source_links`` [C-II][C-V]. Approval/export goes through the existing
``/ai-outputs/{id}/approve`` gate — no new bypass path. Outputs from
low-confidence sources inherit the flag [C-VII].
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.ai_outputs import (
    _build_source_links,
    _create_ai_output,
)
from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import LAWYER, MANAGER, PARALEGAL, assert_case_access, require_roles
from app.core.security import CurrentUser
from app.llm.generate import LlmError, build_prompt
from app.llm.providers import dispatch, parse_provider_config
from app.models import AiOutput
from app.retriever.retrieve import retrieve

logger = logging.getLogger(__name__)

router = APIRouter()

DocType = Literal["contract", "submission", "engagement_letter", "letter"]

_DOC_TYPE_LABELS = {
    "contract": "عقد",
    "submission": "مذكرة قضائية",
    "engagement_letter": "خطاب توكيل",
    "letter": "خطاب رسمي",
}

_AI_BLOCK_RE = re.compile(r"\{\{AI:\s*(.*?)\}\}", re.DOTALL)
_MISSING_RE = re.compile(r"\{\{(\w+)\}\}")


# ── shared helpers ────────────────────────────────────────────────────────────


async def _load_llm(conn) -> tuple[str, dict, dict, str]:
    """Return (api_key, provider_config, embedding_config, model_label)."""
    firm = await conn.fetchrow(
        "SELECT llm_api_key, llm_provider_config, embedding_config "
        "FROM firm_settings LIMIT 1"
    )
    if firm is None:
        raise ApiError(500, "config_error", "إعدادات المكتب غير موجودة")
    api_key: str = firm["llm_api_key"] or ""
    cfg = parse_provider_config(firm["llm_provider_config"])
    emb_cfg = firm["embedding_config"]
    if isinstance(emb_cfg, str):
        emb_cfg = json.loads(emb_cfg)
    model_label = f"{cfg.get('provider')}/{cfg.get('model')}"
    return api_key, cfg, emb_cfg or {}, model_label


async def _case_context_text(conn, case_id: UUID) -> str:
    """Deterministic structured context for the matter (no LLM) [C-IV]."""
    case = await conn.fetchrow(
        "SELECT title, client_name, case_number, court, case_type, "
        "practice_area, jurisdiction, opposing_counsel, docket_number, stage "
        "FROM cases WHERE id = $1",
        case_id,
    )
    if case is None:
        raise ApiError(404, "not_found", "القضية غير موجودة")
    lines = [f"بيانات القضية: {case['title']}"]
    for label, key in (
        ("العميل", "client_name"), ("رقم القضية", "case_number"),
        ("المحكمة", "court"), ("نوع القضية", "case_type"),
        ("مجال الممارسة", "practice_area"), ("الاختصاص", "jurisdiction"),
        ("محامي الخصم", "opposing_counsel"), ("رقم الدائرة", "docket_number"),
        ("المرحلة", "stage"),
    ):
        if case[key]:
            lines.append(f"{label}: {case[key]}")
    return "\n".join(lines)


def _mark_missing(text: str) -> str:
    """Replace unresolved {{var}} tokens with explicit [MISSING: var] markers —
    never leave them silently blank (FR-106)."""
    return _MISSING_RE.sub(lambda m: f"[MISSING: {m.group(1)}]", text)


async def _case_low_confidence(conn, case_id: UUID) -> bool:
    """True if any source document on the matter is low-confidence [C-VII]."""
    return bool(await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM documents "
        "WHERE case_id = $1 AND status = 'low_confidence')",
        case_id,
    ))


# ── POST /ai/draft-document (US1) ─────────────────────────────────────────────


class DraftDocumentRequest(BaseModel):
    case_id: UUID
    doc_type: DocType
    template_id: UUID | None = None
    context: str | None = None  # free-text drafting instructions


class AiDocResponse(BaseModel):
    output: AiOutput


@router.post("/ai/draft-document", response_model=AiDocResponse, status_code=201)
async def draft_document(
    body: DraftDocumentRequest,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL))],
) -> AiDocResponse:
    await assert_case_access(conn, user, body.case_id)
    api_key, cfg, emb_cfg, model_label = await _load_llm(conn)

    # Optional template pass 1: deterministic merge before the AI pass.
    template_body = ""
    if body.template_id is not None:
        tpl = await conn.fetchval(
            "SELECT content FROM document_templates WHERE id = $1 AND is_active",
            body.template_id,
        )
        if tpl is None:
            raise ApiError(404, "not_found", "النموذج غير موجود أو غير نشط")
        template_body = tpl

    case_text = await _case_context_text(conn, body.case_id)
    doc_label = _DOC_TYPE_LABELS[body.doc_type]

    retrieval_query = f"{doc_label} — {case_text}" + (
        f"\n{body.context}" if body.context else ""
    )
    chunks = await retrieve(
        query=retrieval_query,
        conn=conn,
        api_key=api_key,
        embedding_config=emb_cfg,
        case_id=body.case_id,
        include_shared=True,  # Egyptian-law corpus as persuasive reference [C-IX]
    )

    instruction = (
        f"صِغ مسودة {doc_label} باللغة العربية لهذه القضية.\n{case_text}\n"
        + (f"\nتعليمات إضافية من المحامي: {body.context}\n" if body.context else "")
        + (
            f"\nاستخدم البنية التالية كنموذج (استبدل المتغيرات الناقصة بـ "
            f"[MISSING: اسم_المتغير]):\n{template_body}\n"
            if template_body else ""
        )
        + "\nاستند في كل بند جوهري إلى [مصدر N]. "
        "أي اقتباس من القانون المصري هو استشهاد غير ملزم. "
        "لا تتنبأ بأي نتيجة قضائية."  # [C-VIII][C-IX]
    )
    prompt = build_prompt(instruction, [c.chunk_text for c in chunks])

    try:
        raw = await dispatch(prompt, api_key=api_key, provider_config=cfg)
    except LlmError as exc:
        raise ApiError(502, "llm_error", str(exc)) from exc

    output = await _create_ai_output(
        conn,
        document_id=None,
        case_id=body.case_id,
        output_type="doc_draft",
        content={
            "doc_type": body.doc_type,
            "template_id": str(body.template_id) if body.template_id else None,
            "draft": _mark_missing(raw),
        },
        source_links=_build_source_links(chunks),
        low_confidence_flag=await _case_low_confidence(conn, body.case_id),
        model=model_label,
    )
    return AiDocResponse(output=output)


# ── POST /ai/letter-pack (US12) ───────────────────────────────────────────────


class LetterPackRequest(BaseModel):
    case_id: UUID
    template_id: UUID
    context: str | None = None


@router.post("/ai/letter-pack", response_model=AiDocResponse, status_code=201)
async def letter_pack(
    body: LetterPackRequest,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL))],
) -> AiDocResponse:
    """Pass 1: deterministic merge-field substitution from matter data.
    Pass 2: AI fills only the ``{{AI: …}}`` blocks. [C-II][C-IV]"""
    await assert_case_access(conn, user, body.case_id)
    api_key, cfg, emb_cfg, model_label = await _load_llm(conn)

    tpl = await conn.fetchrow(
        "SELECT content, name_ar FROM document_templates "
        "WHERE id = $1 AND is_active",
        body.template_id,
    )
    if tpl is None:
        raise ApiError(404, "not_found", "النموذج غير موجود أو غير نشط")

    case = await conn.fetchrow(
        "SELECT title, client_name, case_number, court, case_type, "
        "opposing_counsel, docket_number FROM cases WHERE id = $1",
        body.case_id,
    )
    if case is None:
        raise ApiError(404, "not_found", "القضية غير موجودة")

    # Pass 1 — deterministic substitution (no LLM) [C-IV].
    rendered = tpl["content"]
    for key, value in dict(case).items():
        if value:
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))

    # Pass 2 — AI blocks, grounded in the matter's corpus.
    ai_blocks = _AI_BLOCK_RE.findall(rendered)
    chunks = []
    if ai_blocks:
        case_text = await _case_context_text(conn, body.case_id)
        chunks = await retrieve(
            query="\n".join(ai_blocks) + "\n" + case_text,
            conn=conn,
            api_key=api_key,
            embedding_config=emb_cfg,
            case_id=body.case_id,
            include_shared=True,
        )
        for block in ai_blocks:
            instruction = (
                f"{await _case_context_text(conn, body.case_id)}\n"
                + (f"تعليمات إضافية: {body.context}\n" if body.context else "")
                + f"اكتب الفقرة المطلوبة التالية فقط (دون مقدمات): {block}\n"
                "استند إلى [مصدر N] حيث يلزم. لا تتنبأ بأي نتيجة قضائية."
            )
            prompt = build_prompt(instruction, [c.chunk_text for c in chunks])
            try:
                filled = await dispatch(prompt, api_key=api_key, provider_config=cfg)
            except LlmError as exc:
                raise ApiError(502, "llm_error", str(exc)) from exc
            rendered = rendered.replace(f"{{{{AI: {block}}}}}", filled, 1)
        # Tolerate whitespace variants of the AI token that .replace missed.
        rendered = _AI_BLOCK_RE.sub("[MISSING: AI_block]", rendered)

    output = await _create_ai_output(
        conn,
        document_id=None,
        case_id=body.case_id,
        output_type="letter_pack",
        content={
            "template_id": str(body.template_id),
            "template_name": tpl["name_ar"],
            "letter": _mark_missing(rendered),
        },
        source_links=_build_source_links(chunks),
        low_confidence_flag=await _case_low_confidence(conn, body.case_id),
        model=model_label,
    )
    return AiDocResponse(output=output)


# ── POST /ai/case-timeline (US13) ─────────────────────────────────────────────


class CaseTimelineRequest(BaseModel):
    case_id: UUID


@router.post("/ai/case-timeline", response_model=AiDocResponse, status_code=201)
async def case_timeline(
    body: CaseTimelineRequest,
    conn: Db,
    user: Annotated[CurrentUser, Depends(require_roles(MANAGER, LAWYER, PARALEGAL))],
) -> AiDocResponse:
    """Chronological matter timeline from document chunks + structured records.

    Structured events (hearings, deadlines) are gathered deterministically and
    cited by record id inside the content; document-derived events cite chunks
    via source_links [C-V]."""
    await assert_case_access(conn, user, body.case_id)
    api_key, cfg, emb_cfg, model_label = await _load_llm(conn)

    case_text = await _case_context_text(conn, body.case_id)

    # Structured events — deterministic, no LLM needed to *select* them [C-IV].
    hearings = await conn.fetch(
        "SELECT id, hearing_date, court_name, status, result FROM hearings "
        "WHERE case_id = $1 ORDER BY hearing_date",
        body.case_id,
    )
    deadlines = await conn.fetch(
        "SELECT id, title, due_date, confirmed FROM deadlines "
        "WHERE case_id = $1 ORDER BY due_date",
        body.case_id,
    )
    structured_lines = [
        f"[سجل جلسة {r['id']}] جلسة بتاريخ {r['hearing_date']:%Y-%m-%d} "
        f"({r['court_name']}) — الحالة: {r['status']}"
        + (f" — النتيجة: {r['result']}" if r["result"] else "")
        for r in hearings
    ] + [
        f"[سجل موعد {r['id']}] استحقاق «{r['title']}» بتاريخ {r['due_date']:%Y-%m-%d}"
        for r in deadlines
    ]

    chunks = await retrieve(
        query=f"تواريخ وأحداث ووقائع {case_text}",
        conn=conn,
        api_key=api_key,
        embedding_config=emb_cfg,
        case_id=body.case_id,
        include_shared=False,  # timeline is matter-scoped facts only
    )
    if not chunks and not structured_lines:
        raise ApiError(
            422, "no_sources",
            "لا توجد مستندات أو سجلات لهذه القضية لاستخراج خط زمني",
        )

    instruction = (
        f"{case_text}\n\nالسجلات المنظَّمة:\n" + "\n".join(structured_lines) +
        "\n\nاستخرج كل الأحداث المؤرَّخة من المقاطع والسجلات أعلاه ورتبها "
        "زمنيًا تصاعديًا. أعد JSON بالشكل:\n"
        '{"timeline": [{"date": "YYYY-MM-DD", "event": "...", '
        '"source": "[مصدر N] أو [سجل ...]"}]}\n'
        "كل حدث يجب أن يُسند إلى مصدره. لا تضف أحداثًا غير واردة في المصادر."
    )
    prompt = build_prompt(instruction, [c.chunk_text for c in chunks])

    try:
        raw = await dispatch(prompt, api_key=api_key, provider_config=cfg)
    except LlmError as exc:
        raise ApiError(502, "llm_error", str(exc)) from exc

    # Best-effort JSON extraction; fall back to raw text.
    timeline_content: dict
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            timeline_content = json.loads(match.group(0))
        except json.JSONDecodeError:
            timeline_content = {"raw": raw}
    else:
        timeline_content = {"raw": raw}
    timeline_content["structured_records"] = {
        "hearings": [str(r["id"]) for r in hearings],
        "deadlines": [str(r["id"]) for r in deadlines],
    }

    output = await _create_ai_output(
        conn,
        document_id=None,
        case_id=body.case_id,
        output_type="case_timeline",
        content=timeline_content,
        source_links=_build_source_links(chunks),
        low_confidence_flag=await _case_low_confidence(conn, body.case_id),
        model=model_label,
    )
    return AiDocResponse(output=output)
