"""Pipeline orchestration (T050).

Full document-processing pipeline for one document:

    upload → Storage
      → advance to 'processing'
      → download bytes from Supabase Storage
      → preprocess (validate)
      → Google Document AI OCR
      → confidence gate → status = ready | low_confidence | failed
      → Arabic normalization [R5]
      → chunk (page-aware, overlapping) [R3]
      → embed (Google Generative AI, firm's API key) [R1]
      → write document_chunks (with pgvector embedding)
      → advance document.status

Any unrecoverable error advances the document to 'failed' with an Arabic
error_detail that is surfaced to the user. [C-VII]

All DB mutations run through an audited connection
    ``db_connection(None, context="worker:pipeline")``
so the audit triggers record system-level changes. [C-III]

The embedding is stored as a Postgres vector literal
    "[f1,f2,…,fN]"::vector
via a parameterized ``$1::vector`` placeholder — no additional codec needed.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.db import db_connection
from app.pipeline.chunk import chunk_pages
from app.pipeline.confidence import assess_confidence
from app.pipeline.embed import EmbedError, embed_texts
from app.pipeline.normalize_ar import normalize
from app.pipeline.ocr_documentai import OcrError, ocr_document
from app.pipeline.preprocess import PreprocessError, preprocess

logger = logging.getLogger(__name__)


async def process_document(document_id: UUID) -> None:
    """Process one document through the full ingestion pipeline.

    Designed to be called by the background worker (T043).  On any unrecoverable
    error the document is advanced to 'failed'; on a soft OCR quality issue it
    is advanced to 'low_confidence' with outputs still generated.

    Args:
        document_id: The UUID of a ``documents`` row currently in 'pending'.
    """
    settings = get_settings()

    async with db_connection(None, context="worker:pipeline") as conn:
        # ── 1. load the document row ──────────────────────────────────────────
        row = await conn.fetchrow(
            """
            SELECT id, firm_id, case_id, file_path, file_name, source_type, status,
                   uploaded_by
            FROM documents
            WHERE id = $1
            """,
            document_id,
        )
        if row is None:
            logger.warning("pipeline: document %s not found — skipping", document_id)
            return

        if row["status"] != "pending":
            logger.debug(
                "pipeline: document %s already %s — skipping",
                document_id,
                row["status"],
            )
            return

        # ── 2. advance to 'processing' ────────────────────────────────────────
        advanced = await conn.fetchval(
            """
            UPDATE documents
            SET status = 'processing', updated_at = now()
            WHERE id = $1 AND status = 'pending'
            RETURNING id
            """,
            document_id,
        )
        if advanced is None:
            logger.debug(
                "pipeline: document %s already claimed — skipping", document_id
            )
            return

        # ── run the pipeline, catching all errors ─────────────────────────────
        try:
            await _run_pipeline(conn, row, settings)
        except (PreprocessError, OcrError, EmbedError, ValueError) as exc:
            await _fail(conn, document_id, str(exc))
        except Exception as exc:
            logger.exception("pipeline: unexpected error for document %s", document_id)
            await _fail(conn, document_id, f"خطأ غير متوقع: {exc}")


async def _run_pipeline(conn, row, settings) -> None:
    """Inner pipeline — assumes document is already 'processing'."""
    document_id: UUID = row["id"]
    file_path: str = row["file_path"]
    source_type: str = row["source_type"]

    # ── 3. download from Supabase Storage ────────────────────────────────────
    raw_bytes, mime_type = await _download_from_storage(
        file_path, row["file_name"], settings
    )

    # ── 4. preprocess (validate) ──────────────────────────────────────────────
    raw_bytes, mime_type = preprocess(raw_bytes, mime_type)

    # ── 5. OCR via Document AI ────────────────────────────────────────────────
    ocr_result = await ocr_document(
        raw_bytes,
        mime_type,
        project_id=settings.docai_project_id,
        location=settings.docai_location,
        processor_id=settings.docai_processor_id,
    )

    # ── 6. confidence gate ────────────────────────────────────────────────────
    final_status = assess_confidence(
        ocr_result.mean_confidence, settings.ocr_confidence_threshold
    )

    # ── 7. Arabic normalization (mandatory) [R5] ──────────────────────────────
    normalized_pages: list[tuple[int, str]] = [
        (page_num, normalize(page_text))
        for page_num, page_text in ocr_result.pages
    ]
    # Drop empty pages after normalization.
    normalized_pages = [(n, t) for n, t in normalized_pages if t.strip()]

    if not normalized_pages:
        # No usable text — treat as failed.
        await _fail(
            conn,
            document_id,
            "لم يتمكن النظام من استخراج نص قابل للمعالجة من المستند",
        )
        return

    # ── 8. chunk [R3] ─────────────────────────────────────────────────────────
    chunks = chunk_pages(
        normalized_pages,
        target_chars=int(settings.chunk_tokens * 3.5),
        overlap_chars=int(settings.chunk_overlap_tokens * 3.5),
    )

    if not chunks:
        await _fail(
            conn, document_id, "لم يتمكن النظام من تقطيع نص المستند"
        )
        return

    # ── 9. read embedding config from firm_settings ───────────────────────────
    firm = await conn.fetchrow(
        "SELECT llm_api_key, embedding_config FROM firm_settings WHERE firm_id = $1",
        row["firm_id"],
    )
    if firm is None:
        await _fail(conn, document_id, "إعدادات المكتب غير موجودة")
        return

    api_key: str = firm["llm_api_key"] or ""
    emb_cfg = firm["embedding_config"]
    if isinstance(emb_cfg, str):
        emb_cfg = json.loads(emb_cfg)
    emb_model: str = (emb_cfg or {}).get("model", "")
    emb_dimension: int = int((emb_cfg or {}).get("dimension", settings.embedding_dimension))

    # ── 10. embed chunks [R1] ─────────────────────────────────────────────────
    texts = [c.text for c in chunks]
    vectors = await embed_texts(
        texts,
        api_key=api_key,
        model=emb_model,
        dimension=emb_dimension,
    )

    # ── 11. store document_chunks in the DB ───────────────────────────────────
    await _store_chunks(conn, document_id, chunks, vectors)

    # ── 12. advance to final status (ready | low_confidence) ─────────────────
    await conn.execute(
        """
        UPDATE documents
        SET status = $2,
            ocr_confidence = $3,
            updated_at = now()
        WHERE id = $1
        """,
        document_id,
        final_status,
        ocr_result.mean_confidence,
    )
    logger.info(
        "pipeline: document %s complete — status=%s pages=%d chunks=%d",
        document_id,
        final_status,
        len(normalized_pages),
        len(chunks),
    )


async def _store_chunks(conn, document_id: UUID, chunks, vectors: list[list[float]]) -> None:
    """Insert document_chunks with vector embeddings.

    Vectors are passed as Postgres vector literals (``"[f1,f2,…]"::vector``)
    because asyncpg has no built-in pgvector codec.
    """
    # Delete any stale chunks from a previous (failed) attempt.
    await conn.execute("DELETE FROM document_chunks WHERE document_id = $1", document_id)

    for chunk, vec in zip(chunks, vectors):
        vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
        await conn.execute(
            """
            INSERT INTO document_chunks
                (document_id, chunk_index, chunk_text, embedding, page_ref, source_location)
            VALUES
                ($1, $2, $3, $4::vector, $5, $6)
            """,
            document_id,
            chunk.index,
            chunk.text,
            vec_literal,
            chunk.page_ref,
            json.dumps({"page": chunk.page_ref, "char_start": chunk.char_start}),
        )


async def _fail(conn, document_id: UUID, error_detail: str) -> None:
    """Advance a document to 'failed' with a user-visible error message."""
    await conn.execute(
        """
        UPDATE documents
        SET status = 'failed', error_detail = $2, updated_at = now()
        WHERE id = $1
        """,
        document_id,
        error_detail,
    )
    logger.warning("pipeline: document %s failed — %s", document_id, error_detail)


async def _download_from_storage(
    file_path: str, file_name: str, settings
) -> tuple[bytes, str]:
    """Download a file from Supabase Storage and return (bytes, mime_type).

    Uses the service key to bypass RLS — the pipeline worker is a trusted
    system actor, not an end user.
    """
    url = (
        f"{settings.supabase_url}/storage/v1/object/"
        f"{settings.storage_bucket}/{file_path}"
    )
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(
                url,
                headers={
                    "authorization": f"Bearer {settings.supabase_service_key}",
                    "apikey": settings.supabase_service_key,
                },
            )
    except httpx.HTTPError as exc:
        raise OcrError(f"تعذّر تحميل الملف من التخزين: {exc}") from exc

    if resp.status_code != 200:
        raise OcrError(
            f"تعذّر تحميل الملف من التخزين — الخادم أعاد {resp.status_code}"
        )

    raw_bytes = resp.content
    mime_type = (
        resp.headers.get("content-type", "application/octet-stream")
        .split(";")[0]
        .strip()
        .lower()
    )
    # Fall back to PDF for unknown types if the file name suggests it.
    if mime_type == "application/octet-stream" and file_name.lower().endswith(".pdf"):
        mime_type = "application/pdf"

    return raw_bytes, mime_type
