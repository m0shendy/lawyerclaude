"""Google Document AI OCR client (T045).

Sends a document to Google Document AI Enterprise Document OCR and returns
structured text with per-page segmentation and a mean confidence score.

Authentication
--------------
Uses Application Default Credentials (ADC) via the
``GOOGLE_APPLICATION_CREDENTIALS`` env var pointing to a service-account JSON.
The credentials are loaded once and refreshed automatically (token TTL ~1 h).
No ``google-cloud-documentai`` gRPC library required — we call the REST API
directly via httpx with a bearer token from ``google-auth``.

Confidence
----------
Document AI returns per-paragraph ``layout.confidence`` values.  We compute
the mean across all paragraphs on all pages.  If confidence data is missing
(text-native PDFs sometimes lack it), we return ``None`` — the confidence gate
in ``confidence.py`` treats ``None`` as high-confidence.

Per-page text extraction
------------------------
Document AI returns a single flattened ``document.text`` string together with
``pages[*].layout.textAnchor.textSegments`` that map each page back to
character offsets in that string.  We use those offsets to reconstruct
page-segmented text for the chunker.

Phase-1 checkpoint note
-----------------------
After implementing this module, you MUST run T052 (the hard-stop checkpoint):
test Document AI on real samples of the firm's actual scans and validate the
mean confidence values before enabling any downstream AI features.  The
``OCR_CONFIDENCE_THRESHOLD`` env var (default 0.80) gates this. [C-VII]
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# Module-level credential cache to avoid re-loading the JSON key on every call.
_creds_holder: list = [None]  # index 0 = google.auth.credentials.Credentials
_creds_lock = asyncio.Lock()


async def _get_access_token() -> str:
    """Return a valid OAuth2 bearer token, refreshing if expired.

    Runs the synchronous google-auth calls in a thread pool to keep the
    event loop unblocked.
    """
    async with _creds_lock:
        def _sync_refresh():
            import google.auth
            import google.auth.transport.requests

            if _creds_holder[0] is None:
                creds, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                _creds_holder[0] = creds

            creds = _creds_holder[0]
            if not creds.valid:
                creds.refresh(google.auth.transport.requests.Request())
            return creds.token

        return await asyncio.to_thread(_sync_refresh)


# ── result types ──────────────────────────────────────────────────────────────


@dataclass
class OcrResult:
    """Structured output from a Document AI OCR call."""

    pages: list[tuple[int, str]]
    """Per-page text as ``[(1-based-page-number, text), ...]``."""
    mean_confidence: float | None
    """Mean paragraph confidence in [0, 1], or ``None`` if unavailable."""
    full_text: str
    """The raw concatenated text from Document AI (for diagnostics)."""


# ── OCR errors ────────────────────────────────────────────────────────────────


class OcrError(Exception):
    """Raised when Document AI returns an error or an unexpected response."""


# ── OCR call ──────────────────────────────────────────────────────────────────


async def ocr_document(
    raw_bytes: bytes,
    mime_type: str,
    *,
    project_id: str,
    location: str,
    processor_id: str,
    timeout: float = 300.0,
) -> OcrResult:
    """Send *raw_bytes* to Document AI and return structured text.

    Args:
        raw_bytes:    Document bytes (PDF or image), already pre-processed.
        mime_type:    Canonical MIME type (e.g. ``"application/pdf"``).
        project_id:   GCP project ID (``settings.docai_project_id``).
        location:     Processor location (``settings.docai_location``).
        processor_id: Processor ID (``settings.docai_processor_id``).
        timeout:      HTTP timeout in seconds.  Large scanned PDFs can take
                      several minutes.

    Returns:
        :class:`OcrResult` with per-page text and confidence.

    Raises:
        OcrError: On Document AI API errors or missing configuration.
    """
    if not project_id or not processor_id:
        raise OcrError(
            "إعدادات Google Document AI غير مكتملة — "
            "تحقق من DOCAI_PROJECT_ID و DOCAI_PROCESSOR_ID"
        )

    processor_name = (
        f"projects/{project_id}/locations/{location}/processors/{processor_id}"
    )
    # Document AI requires the REGIONAL endpoint (e.g. eu-documentai.googleapis.com);
    # the global documentai.googleapis.com host fails for regional processors.
    url = f"https://{location}-documentai.googleapis.com/v1/{processor_name}:process"

    content_b64 = base64.b64encode(raw_bytes).decode("ascii")
    body = {
        "rawDocument": {
            "content": content_b64,
            "mimeType": mime_type,
        }
    }

    access_token = await _get_access_token()

    logger.debug(
        "documentai: sending %d bytes (%s) to processor %s",
        len(raw_bytes),
        mime_type,
        processor_id,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                json=body,
            )
    except httpx.HTTPError as exc:
        raise OcrError(f"طلب Document AI فشل (شبكة): {exc}") from exc

    if resp.status_code != 200:
        raise OcrError(
            f"Document AI أعاد خطأ {resp.status_code}: "
            f"{resp.text[:500]}"
        )

    data = resp.json()
    doc = data.get("document", {})

    full_text: str = doc.get("text", "")
    pages_raw: list[dict] = doc.get("pages", [])

    page_texts = _extract_page_texts(full_text, pages_raw)
    mean_conf = _mean_confidence(pages_raw)

    logger.info(
        "documentai: pages=%d confidence=%.3f text_chars=%d",
        len(page_texts),
        mean_conf if mean_conf is not None else -1.0,
        len(full_text),
    )

    return OcrResult(
        pages=page_texts,
        mean_confidence=mean_conf,
        full_text=full_text,
    )


# ── response parsers ──────────────────────────────────────────────────────────


def _extract_page_texts(full_text: str, pages: list[dict]) -> list[tuple[int, str]]:
    """Map Document AI page anchors back to page-segmented text.

    Falls back to the full text as page 1 when anchor data is absent
    (e.g. some text-native PDF responses).
    """
    result: list[tuple[int, str]] = []

    for page in pages:
        page_num: int = page.get("pageNumber", len(result) + 1)
        anchor: dict = page.get("layout", {}).get("textAnchor", {})
        segments: list[dict] = anchor.get("textSegments", [])

        if segments:
            page_text = ""
            for seg in segments:
                start = int(seg.get("startIndex", 0))
                end = int(seg.get("endIndex", len(full_text)))
                page_text += full_text[start:end]
        elif not result:
            # Single-page document without textAnchor — use full text.
            page_text = full_text
        else:
            page_text = ""

        if page_text.strip():
            result.append((page_num, page_text))

    if not result and full_text.strip():
        result.append((1, full_text))

    return result


def _mean_confidence(pages: list[dict]) -> float | None:
    """Compute mean layout confidence across all paragraphs on all pages.

    Returns ``None`` if no confidence values are present (text-native PDFs
    often omit them).
    """
    confidences: list[float] = []

    for page in pages:
        for para in page.get("paragraphs", []):
            conf = para.get("layout", {}).get("confidence")
            if conf is not None:
                confidences.append(float(conf))
        # Fall back to block-level if no paragraph confidences.
        if not confidences:
            for block in page.get("blocks", []):
                conf = block.get("layout", {}).get("confidence")
                if conf is not None:
                    confidences.append(float(conf))
        # Fall back to token level.
        if not confidences:
            for token in page.get("tokens", []):
                conf = token.get("layout", {}).get("confidence")
                if conf is not None:
                    confidences.append(float(conf))

    return (sum(confidences) / len(confidences)) if confidences else None
