"""Retriever — Component A (T053). [C-V] [R2] [R12]

The Retriever is DETERMINISTIC APPLICATION CODE, not the LLM.  It:
  1. Normalizes the query text (same Arabic rules as document ingestion).
  2. Embeds the query using the firm's configured embedding model.
  3. Searches pgvector across the firm's PRIVATE corpus (document_chunks +
     reference_chunks) using an HNSW cosine-similarity index.
  4. Optionally also queries the SHARED Egyptian-law corpus (read-only,
     public law only) when a second DB connection is available.
  5. Returns ranked chunks with source references for LLM grounding.

The retriever NEVER generates text; that is Component B (llm/generate.py).
Every AI claim must link back to an exact chunk returned here.  [C-V]

RAG scoping
-----------
* Document-level queries (summarize, extract): retrieve chunks from the
  target document only.
* Case-level queries (assistant, analysis): retrieve from all documents
  assigned to the case, respecting caller's case_assignments.
* Reference queries (cross-corpus): both private + shared corpora.

Shared corpus
-------------
When ``settings.shared_corpus_database_url`` is non-empty a second asyncpg
connection reads the central read-only corpus DB.  Public law only — no firm
data ever enters it.  [C-I]
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from app.core.config import get_settings
from app.core.db import get_pool
from app.pipeline.embed import EmbedError, embed_texts
from app.pipeline.normalize_ar import normalize

logger = logging.getLogger(__name__)


# ── result type ───────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class RetrievedChunk:
    """One retrieved chunk with its grounding reference."""

    chunk_id: UUID
    document_id: UUID
    chunk_text: str
    page_ref: int | None
    source_location: dict | None
    similarity: float
    corpus: str  # "private" | "shared"


# ── public API ────────────────────────────────────────────────────────────────


async def retrieve(
    query: str,
    *,
    conn: asyncpg.Connection,
    api_key: str,
    embedding_config: dict,
    top_k: int = 8,
    document_id: UUID | None = None,
    case_id: UUID | None = None,
    include_shared: bool = True,
) -> list[RetrievedChunk]:
    """Return the top-*k* most relevant chunks for *query*.

    Args:
        query:            Natural-language query (Arabic or mixed).
        conn:             DB connection for the firm's private corpus.
        api_key:          Firm's LLM API key (from firm_settings).
        embedding_config: ``{"model": "...", "dimension": 1536}``
        top_k:            Number of chunks to return per corpus.
        document_id:      If set, restrict to chunks of this document.
        case_id:          If set, restrict to documents of this case.
        include_shared:   Whether to also query the shared corpus.

    Returns:
        Chunks sorted by similarity descending (private + shared merged).
    """
    model: str = (embedding_config or {}).get("model", "")
    dimension: int = int((embedding_config or {}).get("dimension", 1536))

    # Normalize the query the same way documents were normalized.
    normalized_query = normalize(query)

    # Embed the query (task_type=RETRIEVAL_QUERY).
    try:
        vecs = await embed_texts(
            [normalized_query],
            api_key=api_key,
            model=model,
            dimension=dimension,
            task_type="RETRIEVAL_QUERY",
        )
    except EmbedError as exc:
        logger.error("retriever: embed query failed: %s", exc)
        raise

    query_vec = vecs[0]
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in query_vec) + "]"

    # Search the private corpus.
    private_chunks = await _search_private(
        conn, vec_literal, top_k=top_k, document_id=document_id, case_id=case_id
    )

    # Search the shared corpus if configured.
    shared_chunks: list[RetrievedChunk] = []
    if include_shared:
        shared_chunks = await _search_shared(vec_literal, top_k=top_k)

    # Merge and re-rank by similarity.
    all_chunks = sorted(
        private_chunks + shared_chunks,
        key=lambda c: c.similarity,
        reverse=True,
    )[:top_k]

    logger.debug(
        "retriever: query=%r private=%d shared=%d returned=%d",
        query[:50],
        len(private_chunks),
        len(shared_chunks),
        len(all_chunks),
    )
    return all_chunks


# ── private corpus search ─────────────────────────────────────────────────────


async def _search_private(
    conn: asyncpg.Connection,
    vec_literal: str,
    *,
    top_k: int,
    document_id: UUID | None,
    case_id: UUID | None,
) -> list[RetrievedChunk]:
    """HNSW cosine similarity search over document_chunks + reference_chunks."""
    conditions = []
    params: list = [vec_literal, top_k]

    # Scope to a specific document if requested.
    if document_id is not None:
        params.append(document_id)
        conditions.append(f"dc.document_id = ${len(params)}")

    # Scope to a specific case's documents if requested.
    elif case_id is not None:
        params.append(case_id)
        conditions.append(f"d.case_id = ${len(params)}")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # document_chunks (firm private corpus, linked to uploaded documents).
    doc_rows = await conn.fetch(
        f"""
        SELECT
            dc.id          AS chunk_id,
            dc.document_id,
            dc.chunk_text,
            dc.page_ref,
            dc.source_location,
            1 - (dc.embedding <=> $1::vector) AS similarity
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        {where}
        ORDER BY dc.embedding <=> $1::vector
        LIMIT $2
        """,
        *params,
    )

    chunks = [
        RetrievedChunk(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            chunk_text=r["chunk_text"],
            page_ref=r["page_ref"],
            source_location=_parse_json(r["source_location"]),
            similarity=float(r["similarity"]),
            corpus="private",
        )
        for r in doc_rows
    ]

    # Also search reference_chunks (firm's own private reference library).
    if document_id is None:  # reference chunks are not per-document
        ref_params: list = [vec_literal, top_k]
        if case_id is not None:
            # References are firm-wide — include all for now; can scope later.
            pass
        ref_rows = await conn.fetch(
            """
            SELECT
                rc.id            AS chunk_id,
                rp.id            AS document_id,   -- treat reference_id as doc_id for grounding
                rc.chunk_text,
                rc.page_ref,
                rc.source_location,
                GREATEST(0.0, LEAST(1.0, 1 - (rc.embedding <=> $1::vector))) AS similarity
            FROM reference_chunks rc
            JOIN references_private rp ON rp.id = rc.reference_id
            ORDER BY rc.embedding <=> $1::vector
            LIMIT $2
            """,
            *ref_params,
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


# ── shared corpus search ──────────────────────────────────────────────────────


async def _search_shared(vec_literal: str, *, top_k: int) -> list[RetrievedChunk]:
    """Search the central read-only Egyptian-law corpus.

    Returns an empty list if ``shared_corpus_database_url`` is not configured
    or if the connection fails (shared corpus is optional / advisory).
    Public law only — no firm data ever enters it.  [C-I]
    """
    settings = get_settings()
    if not settings.shared_corpus_database_url:
        return []

    try:
        conn: asyncpg.Connection = await asyncpg.connect(
            settings.shared_corpus_database_url
        )
    except Exception as exc:
        logger.warning("retriever: shared corpus unavailable: %s", exc)
        return []

    try:
        rows = await conn.fetch(
            """
            SELECT
                cc.id           AS chunk_id,
                cc.document_id  AS document_id,
                cc.chunk_text,
                cc.page_ref,
                cc.source_location,
                GREATEST(0.0, LEAST(1.0, 1 - (cc.embedding <=> $1::vector))) AS similarity
            FROM corpus_chunks cc
            ORDER BY cc.embedding <=> $1::vector
            LIMIT $2
            """,
            vec_literal,
            top_k,
        )
    except Exception as exc:
        logger.warning("retriever: shared corpus query failed: %s", exc)
        return []
    finally:
        await conn.close()

    return [
        RetrievedChunk(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            chunk_text=r["chunk_text"],
            page_ref=r["page_ref"],
            source_location=_parse_json(r["source_location"]),
            similarity=float(r["similarity"]),
            corpus="shared",
        )
        for r in rows
    ]


def _parse_json(value) -> dict | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    if isinstance(value, dict):
        return value
    return None
