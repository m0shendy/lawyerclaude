"""Scoped retrieval for the conversational assistant (T084). [C-I][C-V]

The base Retriever (``retrieve.py``) can scope to a single document or a single
case. The assistant needs **caller-scoped** retrieval: a non-manager may only
ground answers in documents of the cases they are *assigned* to
(``case_assignments``); a manager sees all firm cases. This module enforces that
boundary in deterministic SQL before any chunk reaches the LLM. [C-I]

Firm-wide private references and the shared public-law corpus are not case-bound
and remain available to every caller (RLS already allows them).
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

from app.core.rbac import MANAGER
from app.core.security import CurrentUser
from app.pipeline.embed import embed_texts
from app.pipeline.normalize_ar import normalize
from app.retriever.retrieve import RetrievedChunk, _parse_json, _search_shared

logger = logging.getLogger(__name__)


async def accessible_case_ids(
    conn: asyncpg.Connection, user: CurrentUser
) -> list[UUID] | None:
    """Cases the caller may ground answers in.

    Returns ``None`` for managers (meaning "all cases — no filter"), otherwise
    the explicit list of the caller's assigned case ids (possibly empty).
    """
    if user.role == MANAGER:
        return None
    rows = await conn.fetch(
        "SELECT case_id FROM case_assignments WHERE user_id = $1", user.id
    )
    return [r["case_id"] for r in rows]


async def retrieve_scoped(
    query: str,
    *,
    conn: asyncpg.Connection,
    user: CurrentUser,
    api_key: str,
    embedding_config: dict,
    case_id: UUID | None = None,
    top_k: int = 8,
    include_shared: bool = True,
) -> list[RetrievedChunk]:
    """Retrieve chunks the caller is allowed to see, ranked by similarity. [C-I]"""
    allowed = await accessible_case_ids(conn, user)  # None = all (manager)

    if case_id is not None:
        # Explicit case must be within the caller's scope.
        if allowed is not None and case_id not in allowed:
            return []
        case_ids: list[UUID] | None = [case_id]
    else:
        case_ids = allowed  # None = all, [] = none, or explicit list

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

    private = await _search_private_scoped(
        conn, vec_literal, top_k=top_k, case_ids=case_ids
    )
    shared = await _search_shared(vec_literal, top_k=top_k) if include_shared else []

    merged = sorted(private + shared, key=lambda c: c.similarity, reverse=True)[:top_k]
    logger.debug(
        "scoped-retriever: user=%s role=%s case=%s private=%d shared=%d -> %d",
        user.id, user.role, case_id, len(private), len(shared), len(merged),
    )
    return merged


async def _search_private_scoped(
    conn: asyncpg.Connection,
    vec_literal: str,
    *,
    top_k: int,
    case_ids: list[UUID] | None,
) -> list[RetrievedChunk]:
    """Private-corpus search restricted to the caller's accessible cases.

    ``case_ids`` semantics: ``None`` → all documents (manager); ``[]`` → no case
    documents (caller has no assignments) so only firm-wide references apply; a
    non-empty list → documents of those cases only.
    """
    chunks: list[RetrievedChunk] = []

    # Document chunks — case-scoped.
    if case_ids is None:
        doc_rows = await conn.fetch(
            """
            SELECT dc.id AS chunk_id, dc.document_id, dc.chunk_text, dc.page_ref,
                   dc.source_location, 1 - (dc.embedding <=> $1::vector) AS similarity
            FROM document_chunks dc
            ORDER BY dc.embedding <=> $1::vector
            LIMIT $2
            """,
            vec_literal, top_k,
        )
    elif len(case_ids) == 0:
        doc_rows = []
    else:
        doc_rows = await conn.fetch(
            """
            SELECT dc.id AS chunk_id, dc.document_id, dc.chunk_text, dc.page_ref,
                   dc.source_location, 1 - (dc.embedding <=> $1::vector) AS similarity
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.case_id = ANY($3::uuid[])
            ORDER BY dc.embedding <=> $1::vector
            LIMIT $2
            """,
            vec_literal, top_k, case_ids,
        )

    for r in doc_rows:
        chunks.append(
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                chunk_text=r["chunk_text"],
                page_ref=r["page_ref"],
                source_location=_parse_json(r["source_location"]),
                similarity=float(r["similarity"]),
                corpus="private",
            )
        )

    # Firm-wide private references (not case-bound).
    ref_rows = await conn.fetch(
        """
        SELECT rc.id AS chunk_id, rp.id AS document_id, rc.chunk_text, rc.page_ref,
               rc.source_location, 1 - (rc.embedding <=> $1::vector) AS similarity
        FROM reference_chunks rc
        JOIN references_private rp ON rp.id = rc.reference_id
        ORDER BY rc.embedding <=> $1::vector
        LIMIT $2
        """,
        vec_literal, top_k,
    )
    for r in ref_rows:
        chunks.append(
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                chunk_text=r["chunk_text"],
                page_ref=r["page_ref"],
                source_location=_parse_json(r["source_location"]),
                similarity=float(r["similarity"]),
                corpus="private",
            )
        )

    return sorted(chunks, key=lambda c: c.similarity, reverse=True)[:top_k]
