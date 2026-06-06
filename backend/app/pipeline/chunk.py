"""Token-aware Arabic chunking (T048). [R3] [C-V]

Splits normalized Arabic text into overlapping chunks suitable for embedding
and retrieval.  Each chunk records the source page reference so AI claims can
be grounded to an exact location in the original document. [C-V]

Algorithm
---------
Input: list of (page_number, normalized_text) pairs from the OCR step.
       Text MUST already be normalized (normalize_ar.normalize) before chunking.

1. Paragraph splitting: split each page's text by double-newline boundaries,
   keeping the originating page number with each paragraph.

2. Greedy merging: accumulate paragraphs into a chunk until the character
   count would exceed ``target_chars``.  When the budget is exceeded, emit the
   current chunk and start a new one with the overlap tail of the last
   paragraph (or the last ``overlap_chars`` characters of the accumulated text).

3. Overlap: each chunk (except the first) starts with the last
   ``overlap_chars`` characters of the previous chunk so retrieval does not
   split a clause across a hard boundary.

Character-to-token approximation (R3)
--------------------------------------
Arabic text with multilingual tokenizers averages ≈ 3–5 chars/token.
We use a conservative 3.5 chars/token:
  * target  800 tokens  ≈  2 800 chars  (default ``target_chars``)
  * overlap 120 tokens  ≈    420 chars  (default ``overlap_chars``)

These defaults match research.md R3 and can be tuned at the Phase-1
OCR-checkpoint without code changes (passed from ``Settings``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Paragraph boundary: two or more consecutive newlines (normalizer reduces to ≤ 2).
_PARA_SEP = re.compile(r"\n{2,}")


@dataclass(slots=True, frozen=True)
class Chunk:
    """One text chunk with its grounding reference."""

    index: int
    """Zero-based sequential index within the document."""
    text: str
    """Normalized Arabic chunk text."""
    page_ref: int
    """1-based page number where this chunk *starts*."""
    char_start: int
    """Character offset of the chunk's first character in the document's
    full concatenated text (for debugging / future richer locators)."""


def _split_paragraphs(page_num: int, text: str) -> list[tuple[int, str]]:
    """Return ``[(page_num, paragraph), ...]`` with empty paragraphs dropped."""
    paras = _PARA_SEP.split(text)
    return [(page_num, p.strip()) for p in paras if p.strip()]


def chunk_pages(
    pages: list[tuple[int, str]],
    target_chars: int = 2800,
    overlap_chars: int = 420,
) -> list[Chunk]:
    """Chunk a list of (page_number, normalized_text) into overlapping Chunks.

    Args:
        pages: Ordered list of ``(1-based-page-number, normalized-text)`` pairs.
        target_chars: Maximum characters per chunk (≈ token budget * 3.5).
        overlap_chars: Characters of overlap carried into the next chunk.

    Returns:
        List of :class:`Chunk` objects ordered by their appearance in the
        document.  The list is empty only if all pages are empty.
    """
    # Collect all paragraphs with page attribution.
    paragraphs: list[tuple[int, str]] = []
    for page_num, text in pages:
        if text.strip():
            paragraphs.extend(_split_paragraphs(page_num, text))

    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_page: int = paragraphs[0][0]
    current_chars: int = 0
    doc_offset: int = 0  # running char offset in the document

    def _emit_chunk(overlap: str = "") -> None:
        nonlocal current_parts, current_page, current_chars, doc_offset
        text = "\n\n".join(current_parts).strip()
        if not text:
            return
        chunks.append(
            Chunk(
                index=len(chunks),
                text=text,
                page_ref=current_page,
                char_start=doc_offset,
            )
        )
        doc_offset += len(text)
        # Reset for the next chunk, seeding with overlap text.
        if overlap:
            current_parts = [overlap]
            current_chars = len(overlap)
        else:
            current_parts = []
            current_chars = 0

    for page_num, para in paragraphs:
        # If a single paragraph is larger than the target, split it by lines
        # (sentences) first, then hard-split any remaining giants.
        para_pieces = _split_large_para(para, target_chars)

        for piece in para_pieces:
            piece_len = len(piece)

            # Would adding this piece overflow the target?
            sep_len = 2 if current_parts else 0  # "\n\n" separator cost
            if current_parts and (current_chars + sep_len + piece_len) > target_chars:
                # Emit current chunk with trailing overlap.
                overlap_text = _tail(current_parts, overlap_chars)
                _emit_chunk(overlap=overlap_text)
                # New chunk inherits the current page (set below).

            if not current_parts:
                # First piece of a new chunk — record its page.
                current_page = page_num

            current_parts.append(piece)
            current_chars += (len(piece) + (2 if len(current_parts) > 1 else 0))

    # Emit whatever remains.
    _emit_chunk()
    return chunks


# ── helpers ───────────────────────────────────────────────────────────────────


def _split_large_para(para: str, target_chars: int) -> list[str]:
    """Break an oversized paragraph into sentence-sized pieces, then hard-split
    any piece that is still larger than ``target_chars``."""
    if len(para) <= target_chars:
        return [para]

    # Split on Arabic/Latin sentence endings.
    _sentence_sep = re.compile(r"(?<=[.!?؟。])\s+")
    sentences = _sentence_sep.split(para)
    if len(sentences) <= 1:
        # No sentence boundary found; hard-split.
        return _hard_split(para, target_chars)

    # Merge sentences up to target.
    result: list[str] = []
    buf: list[str] = []
    buf_chars = 0
    for sent in sentences:
        sep = 1 if buf else 0
        if buf and (buf_chars + sep + len(sent)) > target_chars:
            result.extend(_hard_split(" ".join(buf), target_chars))
            buf = []
            buf_chars = 0
        buf.append(sent)
        buf_chars += len(sent) + sep
    if buf:
        result.extend(_hard_split(" ".join(buf), target_chars))
    return [p for p in result if p.strip()]


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Split *text* on word boundaries not exceeding *max_chars* per piece."""
    words = text.split()
    pieces: list[str] = []
    buf: list[str] = []
    buf_chars = 0
    for word in words:
        sep = 1 if buf else 0
        if buf and (buf_chars + sep + len(word)) > max_chars:
            pieces.append(" ".join(buf))
            buf = []
            buf_chars = 0
        buf.append(word)
        buf_chars += len(word) + sep
    if buf:
        pieces.append(" ".join(buf))
    return [p for p in pieces if p.strip()]


def _tail(parts: list[str], max_chars: int) -> str:
    """Return the last *max_chars* characters of ``'\\n\\n'.join(parts)``."""
    full = "\n\n".join(parts)
    if len(full) <= max_chars:
        return full
    return full[-max_chars:]
