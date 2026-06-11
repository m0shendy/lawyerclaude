"""Conversational assistant endpoint (T086). [C-I][C-II][C-V]

``POST /assistant/query`` — available to all roles, **scoped** to the caller's
cases. Retrieval is deterministic and caller-scoped (``retriever/scoped.py``);
generation is grounded and source-cited (``llm/assistant.py``). The chat answer
itself is ephemeral.

If the caller asks to keep the answer for official use (``save_as_draft``), it is
persisted as an ``ai_outputs`` row of type ``analysis`` in ``draft_unreviewed`` —
so the **review gate still applies** and nothing the assistant produced can be
exported/sent until an assigned lawyer or manager approves it. [C-II]

The WhatsApp inbound channel (T082/T083) shares ``retrieve_scoped`` +
``answer_query`` but is a separate entrypoint; this is the in-app channel.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import assert_case_access
from app.core.security import CurrentUserDep
from app.llm.assistant import answer_query
from app.llm.generate import LlmError
from app.models import SourceLink
from app.pipeline.embed import EmbedError
from app.retriever.scoped import retrieve_scoped

logger = logging.getLogger(__name__)

router = APIRouter()

_NO_GROUNDING = (
    "لا توجد مصادر ضمن نطاق صلاحياتك للإجابة على هذا السؤال. "
    "تأكد من رفع المستندات ذات الصلة ومن تكليفك بالقضية."
)


class AssistantQuery(BaseModel):
    query: str = Field(min_length=1)
    case_id: UUID | None = None
    save_as_draft: bool = False


class AssistantResponse(BaseModel):
    answer: str
    sources: list[SourceLink]
    grounded: bool
    saved_output_id: UUID | None = None


@router.post("/assistant/query", response_model=AssistantResponse)
async def assistant_query(
    body: AssistantQuery,
    user: CurrentUserDep,
    conn: Db,
) -> AssistantResponse:
    if not body.query.strip():
        raise ApiError(400, "bad_request", "السؤال فارغ")

    # If a specific case is named, it must be within the caller's access — return
    # 404 for out-of-scope so existence cannot be probed (mirrors case access).
    if body.case_id is not None:
        await assert_case_access(conn, user, body.case_id)

    from app.core.tenancy import get_firm_config

    firm = await get_firm_config(user.firm_id, "llm_api_key", "embedding_config")
    if firm is None:
        raise ApiError(500, "config_error", "إعدادات المكتب غير موجودة")
    api_key: str = firm["llm_api_key"] or ""
    emb_cfg = firm["embedding_config"]
    if isinstance(emb_cfg, str):
        emb_cfg = json.loads(emb_cfg)
    model = (emb_cfg or {}).get("llm_model", "models/gemini-2.0-flash")

    try:
        chunks = await retrieve_scoped(
            body.query,
            conn=conn,
            user=user,
            api_key=api_key,
            embedding_config=emb_cfg or {},
            case_id=body.case_id,
            top_k=8,
        )
    except EmbedError as exc:
        raise ApiError(502, "embed_error", str(exc)) from exc

    if not chunks:
        return AssistantResponse(answer=_NO_GROUNDING, sources=[], grounded=False)

    try:
        answer = await answer_query(body.query, chunks, api_key=api_key, model=model)
    except LlmError as exc:
        raise ApiError(502, "llm_error", str(exc)) from exc

    sources = [
        SourceLink(chunk_id=c.chunk_id, document_id=c.document_id, page_ref=c.page_ref)
        for c in chunks
    ]

    saved_id: UUID | None = None
    if body.save_as_draft:
        saved_id = await _save_as_draft(
            conn,
            case_id=body.case_id,
            query=body.query,
            answer=answer,
            sources=sources,
            model=model,
        )

    return AssistantResponse(
        answer=answer,
        sources=sources,
        grounded=True,
        saved_output_id=saved_id,
    )


async def _save_as_draft(
    conn,
    *,
    case_id: UUID | None,
    query: str,
    answer: str,
    sources: list[SourceLink],
    model: str,
) -> UUID:
    """Persist the assistant answer as a draft_unreviewed analysis output. [C-II]"""
    content = {"question": query, "answer": answer, "raw_text": answer}
    source_links = [
        {
            "chunk_id": str(s.chunk_id),
            "document_id": str(s.document_id),
            "page_ref": s.page_ref,
        }
        for s in sources
    ]
    output_id = await conn.fetchval(
        """
        INSERT INTO ai_outputs
            (firm_id, document_id, case_id, type, content, source_links,
             review_state, low_confidence_flag, generated_by_model)
        VALUES ($5, NULL, $1, 'analysis', $2, $3, 'draft_unreviewed', false, $4)
        RETURNING id
        """,
        case_id,
        json.dumps(content, ensure_ascii=False),
        json.dumps(source_links, ensure_ascii=False),
        model,
        user.firm_id,
    )
    logger.info("assistant: saved draft output=%s case=%s", output_id, case_id)
    return output_id
