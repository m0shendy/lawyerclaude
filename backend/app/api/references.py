"""Reference search endpoint (T093/T094 surface). [C-IX]

``POST /references/search`` — available to all authenticated roles. Returns
persuasive-only legal references (private library + shared public-law corpus) for
istishhad, each labelled *not binding / not a prediction*. No case content is
ever touched, so nothing crosses the firm boundary.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.db import Db
from app.core.errors import ApiError
from app.core.security import CurrentUserDep
from app.pipeline.embed import EmbedError
from app.retriever.references import match_references

logger = logging.getLogger(__name__)

router = APIRouter()


class ReferenceQuery(BaseModel):
    query: str = Field(min_length=1)


class ReferenceMatchOut(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    page_ref: int | None
    corpus: str
    similarity: float
    label: str


class ReferenceSearchResponse(BaseModel):
    notice: str
    matches: list[ReferenceMatchOut]


@router.post("/references/search", response_model=ReferenceSearchResponse)
async def search_references(
    body: ReferenceQuery,
    user: CurrentUserDep,
    conn: Db,
) -> ReferenceSearchResponse:
    if not body.query.strip():
        raise ApiError(400, "bad_request", "نص البحث فارغ")

    firm = await conn.fetchrow(
        "SELECT llm_api_key, embedding_config FROM firm_settings LIMIT 1"
    )
    if firm is None:
        raise ApiError(500, "config_error", "إعدادات المكتب غير موجودة")
    api_key: str = firm["llm_api_key"] or ""
    emb_cfg = firm["embedding_config"]
    if isinstance(emb_cfg, str):
        emb_cfg = json.loads(emb_cfg)

    try:
        result = await match_references(
            body.query, conn=conn, api_key=api_key, embedding_config=emb_cfg or {}
        )
    except EmbedError as exc:
        raise ApiError(502, "embed_error", str(exc)) from exc

    return ReferenceSearchResponse(
        notice=result.notice,
        matches=[ReferenceMatchOut(**m.__dict__) for m in result.matches],
    )
