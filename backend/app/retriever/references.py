"""Reference matching across private + shared corpora (T093, T094). [C-IX]

Finds legal references/precedents relevant to a query for **istishhad**
(persuasive citation) — from the firm's private reference library and the shared
read-only Egyptian-law corpus. This is deterministic retrieval (Component A): it
does NOT generate text and does NOT touch case documents.

Every result is framed **persuasive-only**: explicitly *not binding* and *not a
prediction of outcome*. [C-IX] The matcher never reaches into case files, so it
cannot leak case content across the firm boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg

from app.pipeline.embed import embed_texts
from app.pipeline.normalize_ar import normalize
from app.retriever.retrieve import RetrievedChunk, _parse_json, _search_shared

logger = logging.getLogger(__name__)

# Surfaced with every result set. [C-IX][C-VIII]
PERSUASIVE_ONLY_NOTICE = (
    "هذه المراجع للاستئناس فقط (استشهاد) وليست مُلزِمة، ولا تُعدّ تنبؤاً بنتيجة. "
    "التقدير القانوني النهائي للمحامي المختص."
)


@dataclass(frozen=True)
class ReferenceMatch:
    chunk_id: str
    document_id: str
    text: str
    page_ref: int | None
    corpus: str          # "private" | "shared"
    similarity: float
    label: str = "للاستئناس فقط — غير مُلزِم"


@dataclass(frozen=True)
class ReferenceResult:
    notice: str
    matches: list[ReferenceMatch]


async def match_references(
    query: str,
    *,
    conn: asyncpg.Connection,
    api_key: str,
    embedding_config: dict,
    top_k: int = 8,
    include_shared: bool = True,
) -> ReferenceResult:
    """Return persuasive-only reference matches for *query* (private refs + shared)."""
    model: str = (embedding_config or {}).get("model", "")
    dimension: int = int((embedding_config or {}).get("dimension", 1536))

    vecs = await embed_texts(
        [normalize(query)],
        api_key=api_key,
        model=model,
        dimension=dimension,
        task_type="RETRIEVAL_QUERY",
    )
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in vecs[0]) + "]"

    private = await _search_private_references(conn, vec_literal, top_k=top_k)
    shared = await _search_shared(vec_literal, top_k=top_k) if include_shared else []

    merged = sorted(private + shared, key=lambda c: c.similarity, reverse=True)[:top_k]
    matches = [
        ReferenceMatch(
            chunk_id=str(c.chunk_id),
            document_id=str(c.document_id),
            text=c.chunk_text,
            page_ref=c.page_ref,
            corpus=c.corpus,
            similarity=round(c.similarity, 4),
        )
        for c in merged
    ]
    return ReferenceResult(notice=PERSUASIVE_ONLY_NOTICE, matches=matches)


async def _search_private_references(
    conn: asyncpg.Connection, vec_literal: str, *, top_k: int
) -> list[RetrievedChunk]:
    """Search ONLY the firm's private reference library (not case documents)."""
    rows = await conn.fetch(
        """
        SELECT rc.id AS chunk_id, rp.id AS document_id, rc.chunk_text, rc.page_ref,
               rc.source_location,
               GREATEST(0.0, LEAST(1.0, 1 - (rc.embedding <=> $1::vector))) AS similarity
        FROM reference_chunks rc
        JOIN references_private rp ON rp.id = rc.reference_id
        ORDER BY rc.embedding <=> $1::vector
        LIMIT $2
        """,
        vec_literal, top_k,
    )
    return [
        RetrievedChunk(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            chunk_text=r["chunk_text"],
            page_ref=r["page_ref"],
            source_location=_parse_json(r["source_location"]),
            similarity=float(r["similarity"]),
            corpus="private",
        )
        for r in rows
    ]
