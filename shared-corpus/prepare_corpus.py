"""One-time shared Egyptian-law corpus preparation tool (T051). [C-I] [R11]

PURPOSE
-------
Prepares the shared, read-only Egyptian-law reference corpus that is provided
to every firm instance.  This script is run ONCE centrally by the operator
(or re-run when the corpus is updated with new legislation).

It MUST NOT be run per-firm or per-instance.  The corpus contains PUBLIC LAW
ONLY — no firm or client data may ever enter it. [C-I]

CORPUS DELIVERY
---------------
After running this script, the embedded chunks are stored in a separate
Postgres database (the shared-corpus DB, pointed to by SHARED_CORPUS_DB_URL).
Each firm instance reads from this DB over the read-only connection configured
in ``settings.shared_corpus_database_url``.

INPUT FILES
-----------
Place source files in a directory (default: ``./corpus-source/``):

  * ``.txt`` files — pre-extracted plain text (e.g. output of Foxit Pro OCR
    or direct PDF text extraction).
  * ``.pdf`` files — text-layer PDFs (text extracted directly; no OCR called).
    Requires ``pypdf`` (``pip install pypdf``).

Image-only files that need OCR should be processed by Foxit Pro FIRST and the
extracted text saved as ``.txt`` before running this script.  The plan notes
that Foxit Pro is used for the one-time shared corpus image files (plan.md).

SCHEMA (shared_corpus DB)
--------------------------
The shared-corpus DB uses a simplified schema:
  * ``corpus_documents``  — one row per source file.
  * ``corpus_chunks``     — chunked, normalized, embedded text with page_ref.

Run ``--init-schema`` to create these tables on the first run.

USAGE
------
    # Install extras if needed:
    pip install pypdf

    # Set env vars:
    export SHARED_CORPUS_DB_URL=postgresql://user:pass@host:5432/shared_corpus
    export GOOGLE_AI_API_KEY=<your_google_api_key>
    export EMBEDDING_MODEL=models/gemini-embedding-exp-03-07
    export EMBEDDING_DIMENSION=1536

    # Create schema (first run only):
    python prepare_corpus.py --init-schema

    # Process all source files:
    python prepare_corpus.py --source ./corpus-source/

    # Dry run (no DB writes):
    python prepare_corpus.py --source ./corpus-source/ --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import httpx

# We import pipeline modules that live in backend/app.
# Run this script from the ``backend/`` directory:
#   cd backend && python ../shared-corpus/prepare_corpus.py ...
try:
    from app.pipeline.chunk import chunk_pages
    from app.pipeline.embed import embed_texts
    from app.pipeline.normalize_ar import normalize
except ImportError as exc:
    print(
        f"[ERROR] Cannot import pipeline modules: {exc}\n"
        "Run this script from the backend/ directory:\n"
        "  cd backend && python ../shared-corpus/prepare_corpus.py ...",
        file=sys.stderr,
    )
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("prepare_corpus")

# ── config (from environment) ────────────────────────────────────────────────

SHARED_CORPUS_DB_URL = os.environ.get("SHARED_CORPUS_DB_URL", "")
GOOGLE_AI_API_KEY    = os.environ.get("GOOGLE_AI_API_KEY", "")
EMBEDDING_MODEL      = os.environ.get("EMBEDDING_MODEL", "models/gemini-embedding-exp-03-07")
EMBEDDING_DIMENSION  = int(os.environ.get("EMBEDDING_DIMENSION", "1536"))
CHUNK_TARGET_CHARS   = int(os.environ.get("CHUNK_TARGET_CHARS", "2800"))   # ≈ 800 tokens
CHUNK_OVERLAP_CHARS  = int(os.environ.get("CHUNK_OVERLAP_CHARS", "420"))   # ≈ 120 tokens


# ── corpus DB schema ──────────────────────────────────────────────────────────

INIT_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS corpus_documents (
    id           BIGSERIAL PRIMARY KEY,
    filename     TEXT NOT NULL UNIQUE,
    sha256       TEXT NOT NULL,
    chunk_count  INT NOT NULL DEFAULT 0,
    indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS corpus_chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES corpus_documents(id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL,
    chunk_text   TEXT NOT NULL,
    embedding    vector({dim}),
    page_ref     INT,
    source_location JSONB,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_corpus_chunks_embedding
    ON corpus_chunks USING hnsw (embedding vector_cosine_ops);

-- Grant read-only access to a dedicated role (firm instances connect as this role).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'corpus_reader') THEN
        CREATE ROLE corpus_reader NOLOGIN;
    END IF;
END $$;
GRANT SELECT ON corpus_documents, corpus_chunks TO corpus_reader;
""".format(dim=EMBEDDING_DIMENSION)


# ── text extraction ───────────────────────────────────────────────────────────


def _extract_text_from_txt(path: Path) -> list[tuple[int, str]]:
    """Read a plain-text file as one page."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [(1, text)]


def _extract_text_from_pdf(path: Path) -> list[tuple[int, str]]:
    """Extract text from a text-layer PDF using pypdf (no OCR)."""
    try:
        import pypdf  # optional dependency
    except ImportError:
        logger.error(
            "pypdf is required for PDF extraction: pip install pypdf\n"
            "For image-based PDFs, use Foxit Pro to export as .txt first."
        )
        raise
    pages: list[tuple[int, str]] = []
    reader = pypdf.PdfReader(str(path))
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((i, text))
    return pages


def extract_text(path: Path) -> list[tuple[int, str]]:
    """Dispatch to the appropriate extractor based on file extension."""
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _extract_text_from_txt(path)
    if suffix == ".pdf":
        return _extract_text_from_pdf(path)
    raise ValueError(f"Unsupported file type: {suffix!r}. Use .txt or .pdf.")


# ── file SHA-256 ──────────────────────────────────────────────────────────────


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


# ── main processing loop ──────────────────────────────────────────────────────


async def process_file(
    conn: asyncpg.Connection,
    path: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Process one source file: normalize → chunk → embed → store."""
    filename = path.name
    file_hash = sha256_of(path)

    # Skip if already indexed with the same content.
    existing = await conn.fetchrow(
        "SELECT id, sha256 FROM corpus_documents WHERE filename = $1", filename
    )
    if existing and existing["sha256"] == file_hash:
        logger.info("skip (unchanged): %s", filename)
        return
    if existing:
        logger.info("re-indexing (changed): %s", filename)

    # 1. Extract text.
    logger.info("extracting text: %s", filename)
    try:
        raw_pages = extract_text(path)
    except Exception as exc:
        logger.error("text extraction failed for %s: %s", filename, exc)
        return

    if not raw_pages:
        logger.warning("no text extracted from %s — skipping", filename)
        return

    # 2. Normalize.
    normalized_pages = [
        (page_num, normalize(text))
        for page_num, text in raw_pages
    ]
    normalized_pages = [(n, t) for n, t in normalized_pages if t.strip()]

    if not normalized_pages:
        logger.warning("all text empty after normalization: %s", filename)
        return

    # 3. Chunk.
    chunks = chunk_pages(
        normalized_pages,
        target_chars=CHUNK_TARGET_CHARS,
        overlap_chars=CHUNK_OVERLAP_CHARS,
    )
    logger.info("  → %d chunks", len(chunks))

    if not chunks:
        logger.warning("no chunks produced for %s", filename)
        return

    # 4. Embed.
    logger.info("  embedding %d chunks...", len(chunks))
    try:
        vectors = await embed_texts(
            [c.text for c in chunks],
            api_key=GOOGLE_AI_API_KEY,
            model=EMBEDDING_MODEL,
            dimension=EMBEDDING_DIMENSION,
            task_type="RETRIEVAL_DOCUMENT",
        )
    except Exception as exc:
        logger.error("embedding failed for %s: %s", filename, exc)
        return

    if dry_run:
        logger.info("  [DRY RUN] would write %d chunks for %s", len(chunks), filename)
        return

    # 5. Write to DB.
    async with conn.transaction():
        # Delete old chunks if re-indexing.
        if existing:
            await conn.execute(
                "DELETE FROM corpus_chunks WHERE document_id = $1", existing["id"]
            )
            await conn.execute(
                "UPDATE corpus_documents SET sha256 = $1, chunk_count = $2, "
                "indexed_at = now() WHERE id = $3",
                file_hash, len(chunks), existing["id"],
            )
            doc_id = existing["id"]
        else:
            doc_id = await conn.fetchval(
                "INSERT INTO corpus_documents (filename, sha256, chunk_count) "
                "VALUES ($1, $2, $3) RETURNING id",
                filename, file_hash, len(chunks),
            )

        for chunk, vec in zip(chunks, vectors):
            vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
            await conn.execute(
                """
                INSERT INTO corpus_chunks
                    (document_id, chunk_index, chunk_text, embedding, page_ref, source_location)
                VALUES ($1, $2, $3, $4::vector, $5, $6)
                """,
                doc_id, chunk.index, chunk.text, vec_literal,
                chunk.page_ref,
                json.dumps({"page": chunk.page_ref, "char_start": chunk.char_start}),
            )

    logger.info("  ✓ indexed %s (%d chunks)", filename, len(chunks))


async def run(source_dir: Path, *, dry_run: bool, init_schema: bool) -> None:
    if not SHARED_CORPUS_DB_URL:
        logger.error("SHARED_CORPUS_DB_URL is not set")
        sys.exit(1)

    conn: asyncpg.Connection = await asyncpg.connect(SHARED_CORPUS_DB_URL)
    try:
        if init_schema:
            logger.info("initializing shared corpus schema...")
            await conn.execute(INIT_SCHEMA_SQL)
            logger.info("schema ready.")

        files = sorted(
            p for p in source_dir.iterdir()
            if p.suffix.lower() in {".txt", ".pdf"} and p.is_file()
        )
        if not files:
            logger.warning("no .txt or .pdf files found in %s", source_dir)
            return

        logger.info(
            "processing %d file(s) from %s (dry_run=%s)...",
            len(files), source_dir, dry_run,
        )
        for path in files:
            await process_file(conn, path, dry_run=dry_run)

        logger.info("done.")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare the shared Egyptian-law corpus (one-time)."
    )
    parser.add_argument(
        "--source",
        default="./corpus-source",
        help="Directory containing .txt / .pdf source files (default: ./corpus-source)",
    )
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Create corpus_documents and corpus_chunks tables (first run only).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process files but do not write to the database.",
    )
    args = parser.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.is_dir():
        print(f"[ERROR] Source directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run(source_dir, dry_run=args.dry_run, init_schema=args.init_schema))


if __name__ == "__main__":
    main()
