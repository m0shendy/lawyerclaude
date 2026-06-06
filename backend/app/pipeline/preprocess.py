"""Document pre-processing step (T044).

Validates and prepares raw bytes for the Document AI OCR step.
Google Document AI (Enterprise Document OCR) handles PDFs and common image
formats natively, so this step is intentionally lightweight:

  * Validate MIME type (must be an allowed format).
  * Enforce the 20 MB inline-content limit that the Document AI sync processor
    enforces.  Documents over that limit need async batch processing (GCS URIs),
    which is a Phase 1 + checkpoint TODO.
  * Return the bytes and the canonical MIME type ready for the OCR call.

For text PDFs (source_type = 'text_pdf'), the OCR step will still be called —
Document AI can extract text from text PDFs more accurately than a naive PDF
text extractor.  Fallback to a pure-Python extractor is a post-checkpoint option
if Document AI is not configured (see run.py).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Document AI Enterprise Document OCR supported MIME types.
SUPPORTED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/tiff",
        "image/gif",
        "image/bmp",
        "image/webp",
    }
)

# Inline-content limit: 20 MB.  Larger files need GCS batch processing.
MAX_INLINE_BYTES: int = 20 * 1024 * 1024  # 20 MiB


class PreprocessError(Exception):
    """Raised when the document cannot be prepared for OCR."""


def preprocess(raw_bytes: bytes, declared_mime_type: str) -> tuple[bytes, str]:
    """Validate and prepare *raw_bytes* for Document AI.

    Args:
        raw_bytes: The raw file content as read from Supabase Storage.
        declared_mime_type: The MIME type stored with the document (from upload).

    Returns:
        A ``(bytes, mime_type)`` tuple ready to pass to the OCR step.

    Raises:
        PreprocessError: If the file is empty, too large, or an unsupported type.
    """
    if not raw_bytes:
        raise PreprocessError("الملف فارغ — يرجى إعادة الرفع")

    # Normalize and validate MIME type.
    mime = declared_mime_type.strip().lower().split(";")[0].strip()
    # Map common aliases.
    mime = "image/jpeg" if mime == "image/jpg" else mime

    if mime not in SUPPORTED_MIME_TYPES:
        raise PreprocessError(
            f"نوع الملف غير مدعوم: {mime!r}. "
            "المقبول: PDF أو JPEG/PNG/TIFF/GIF/BMP/WEBP"
        )

    # Enforce inline-content size limit.
    if len(raw_bytes) > MAX_INLINE_BYTES:
        size_mb = len(raw_bytes) / (1024 * 1024)
        raise PreprocessError(
            f"حجم الملف ({size_mb:.1f} MB) يتجاوز الحد الأقصى المدعوم "
            f"({MAX_INLINE_BYTES // (1024 * 1024)} MB) للمعالجة الفورية. "
            "يرجى تقسيم الملف أو التواصل مع الدعم الفني."
        )

    logger.debug(
        "preprocess ok: mime=%s size=%d bytes", mime, len(raw_bytes)
    )
    return raw_bytes, mime
