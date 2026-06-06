"""OCR confidence gate (T046). [C-VII] [R4]

Applies the configurable threshold to decide whether a document's OCR quality
is sufficient for downstream AI use without an elevated warning.

Decision matrix
---------------
ocr_confidence >= threshold              → status = 'ready'
0 < ocr_confidence < threshold           → status = 'low_confidence'
  (output still possible, but UI shows a stronger warning and may require
   double review — constitution [C-VII])
ocr_confidence is None / hard OCR error  → status = 'failed'
  (no AI output generated — surfaced to user with error_detail)

Default threshold: 0.80 (research.md R4 — tune at the Phase-1 checkpoint after
validating on real scan samples).
"""

from __future__ import annotations

from typing import Literal

DocumentStatus = Literal["ready", "low_confidence", "failed"]


def assess_confidence(
    mean_confidence: float | None,
    threshold: float,
) -> DocumentStatus:
    """Return the document status to set after OCR.

    Args:
        mean_confidence: The mean paragraph confidence returned by Document AI.
            Pass ``None`` if confidence data is unavailable (treated as 'ready'
            because Document AI will only return text when it can extract
            something — caller should treat ``None`` as high-confidence for
            text-native PDFs).
        threshold: The per-instance threshold (from ``settings.ocr_confidence_threshold``).

    Returns:
        ``'ready'``, ``'low_confidence'``, or ``'failed'``.
    """
    if mean_confidence is None:
        # No confidence data → assume text-native PDF; treat as ready.
        return "ready"
    if mean_confidence >= threshold:
        return "ready"
    return "low_confidence"
