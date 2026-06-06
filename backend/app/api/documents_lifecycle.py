"""Document status lifecycle (T035) — pure helpers over a connection.

Legal transitions (rest-api.md):

    pending → processing → ready | low_confidence | failed

No FastAPI deps here: the pipeline worker calls these with a connection from
`db_connection(None, context="worker:pipeline")` so the DB audit triggers
record the system action. Illegal transitions raise ValueError — callers must
never silently skip a state. [C-III][C-VII]
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

LEGAL_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "pending": ("processing",),
    "processing": ("ready", "low_confidence", "failed"),
    "ready": (),
    "low_confidence": (),
    "failed": (),
}


async def advance_status(
    conn: asyncpg.Connection,
    document_id: UUID,
    new_status: str,
    *,
    ocr_confidence: float | None = None,
    error_detail: str | None = None,
) -> None:
    """Advance a document along the status lifecycle.

    Raises:
        ValueError: unknown document, unknown status, or illegal transition.
    """
    if new_status not in LEGAL_TRANSITIONS:
        raise ValueError(f"unknown document status: {new_status!r}")

    current = await conn.fetchval("SELECT status FROM documents WHERE id = $1", document_id)
    if current is None:
        raise ValueError(f"document not found: {document_id}")
    if new_status not in LEGAL_TRANSITIONS[current]:
        raise ValueError(f"illegal document status transition: {current!r} -> {new_status!r}")

    # Compare-and-swap on the expected current status so two concurrent workers
    # cannot both perform the same transition (TOCTOU between read and write).
    updated = await conn.fetchval(
        """
        UPDATE documents
        SET status = $2,
            ocr_confidence = COALESCE($3, ocr_confidence),
            error_detail = $4,
            updated_at = now()
        WHERE id = $1 AND status = $5
        RETURNING id
        """,
        document_id,
        new_status,
        ocr_confidence,
        error_detail,
        current,
    )
    if updated is None:
        raise ValueError(
            f"document status changed concurrently: expected {current!r} "
            f"before transition to {new_status!r} (document {document_id})"
        )
