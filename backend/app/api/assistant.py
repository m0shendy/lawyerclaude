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
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.db import Db, db_connection
from app.core.errors import ApiError
from app.core.rbac import assert_case_access
from app.core.security import CurrentUser, CurrentUserDep
from app.llm.assistant import answer_query
from app.llm.generate import LlmError
from app.models import SourceLink
from app.pipeline.embed import EmbedError
from app.retriever.scoped import retrieve_scoped
from app.scheduler.waha import WahaError, send_text

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

    firm = await conn.fetchrow(
        "SELECT llm_api_key, embedding_config FROM firm_settings LIMIT 1"
    )
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


# ── inbound WhatsApp channel (T082, T083) [C-I] ───────────────────────────────

_REFUSAL = (
    "عذراً، لا يمكنني الرد. هذا الرقم غير مسجَّل كمستخدم نشط في المكتب. "
    "يرجى التواصل مع إدارة المكتب."
)


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


async def _resolve_active_user(conn, phone_digits: str) -> CurrentUser | None:
    """Bind an inbound sender phone to an ACTIVE user, or None. [C-I][C-III]"""
    if not phone_digits:
        return None
    row = await conn.fetchrow(
        """
        SELECT id, auth_user_id, full_name, email, phone,
               role::text AS role, status::text AS status
        FROM users
        WHERE regexp_replace(coalesce(phone, ''), '\\D', '', 'g') = $1
        LIMIT 1
        """,
        phone_digits,
    )
    if row is None or row["status"] != "active":
        return None
    return CurrentUser(**dict(row))


@router.post("/assistant/whatsapp/webhook")
async def whatsapp_webhook(
    body: dict,
    x_webhook_token: Annotated[str | None, Header()] = None,
) -> dict:
    """Inbound WAHA webhook for the conversational assistant. [C-I][C-II][C-V]

    Unregistered/inactive senders get a polite refusal and **zero** case content.
    Registered senders get a grounded, scoped answer delivered back over WhatsApp.
    Runs in a system (BYPASSRLS) context; scoping is enforced in code.
    """
    settings = get_settings()
    if settings.waha_webhook_token and x_webhook_token != settings.waha_webhook_token:
        raise ApiError(401, "unauthorized", "رمز التحقق غير صالح")

    # WAHA "message" event shape: {event, session, payload:{from, body, fromMe}}
    if body.get("event") not in (None, "message", "message.any"):
        return {"status": "ignored"}
    payload = body.get("payload") or {}
    if payload.get("fromMe"):
        return {"status": "ignored"}
    sender = _digits(payload.get("from"))
    text = (payload.get("body") or "").strip()
    if not sender or not text:
        return {"status": "ignored"}

    async with db_connection(None, context="webhook:assistant:whatsapp") as conn:
        user = await _resolve_active_user(conn, sender)
        firm = await conn.fetchrow(
            "SELECT llm_api_key, embedding_config, waha_url, waha_key FROM firm_settings LIMIT 1"
        )

        async def _reply(message: str) -> None:
            if not firm or not firm["waha_url"]:
                logger.warning("whatsapp_webhook: no WAHA url configured; cannot reply")
                return
            try:
                await send_text(
                    waha_url=firm["waha_url"],
                    waha_key=firm["waha_key"],
                    phone=sender,
                    text=message,
                    session=settings.waha_session,
                )
            except WahaError as exc:
                logger.warning("whatsapp_webhook: reply failed: %s", exc)

        # Unregistered/inactive → refuse with no case content. [C-I]
        if user is None:
            await _reply(_REFUSAL)
            return {"status": "refused"}

        api_key = (firm["llm_api_key"] if firm else "") or ""
        emb_cfg = firm["embedding_config"] if firm else {}
        if isinstance(emb_cfg, str):
            emb_cfg = json.loads(emb_cfg)
        model = (emb_cfg or {}).get("llm_model", "models/gemini-2.0-flash")

        try:
            chunks = await retrieve_scoped(
                text, conn=conn, user=user, api_key=api_key,
                embedding_config=emb_cfg or {}, top_k=8,
            )
        except EmbedError as exc:
            logger.warning("whatsapp_webhook: embed failed: %s", exc)
            await _reply("تعذّرت معالجة سؤالك حالياً، حاول لاحقاً.")
            return {"status": "error"}

        if not chunks:
            await _reply(_NO_GROUNDING)
            return {"status": "no_grounding"}

        try:
            answer = await answer_query(text, chunks, api_key=api_key, model=model)
        except LlmError as exc:
            logger.warning("whatsapp_webhook: llm failed: %s", exc)
            await _reply("تعذّر توليد الإجابة حالياً، حاول لاحقاً.")
            return {"status": "error"}

        await _reply(answer)
        return {"status": "answered", "user_id": str(user.id)}


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
            (document_id, case_id, type, content, source_links,
             review_state, low_confidence_flag, generated_by_model)
        VALUES (NULL, $1, 'analysis', $2, $3, 'draft_unreviewed', false, $4)
        RETURNING id
        """,
        case_id,
        json.dumps(content, ensure_ascii=False),
        json.dumps(source_links, ensure_ascii=False),
        model,
    )
    logger.info("assistant: saved draft output=%s case=%s", output_id, case_id)
    return output_id
