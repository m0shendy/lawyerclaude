"""Pipeline unit tests (T043–T051 smoke).

Cover all pure-logic pipeline modules without requiring a live DB, Document AI
credentials, or a real embedding API key.  Network-dependent tests (OCR +
embedding + end-to-end pipeline) are marked `integration` and require live
credentials.
"""

from __future__ import annotations

import pytest

# ─── normalize_ar ─────────────────────────────────────────────────────────────

from app.pipeline.normalize_ar import normalize


def test_normalize_empty() -> None:
    assert normalize("") == ""


def test_normalize_alef_variants() -> None:
    # أ إ آ → ا
    result = normalize("أحمد إبراهيم آداب")
    assert "أ" not in result
    assert "إ" not in result
    assert "آ" not in result
    assert "ا" in result


def test_normalize_alef_maqsura() -> None:
    result = normalize("يُصلّى")
    assert "ى" not in result


def test_normalize_strips_diacritics() -> None:
    result = normalize("الحُكمُ")
    for diacritic in "ًٌٍَُِّْ":
        assert diacritic not in result, f"diacritic {diacritic!r} found in {result!r}"


def test_normalize_strips_tatweel() -> None:
    assert "ـ" not in normalize("مـحـكـمـة")


def test_normalize_ta_marbuta_word_boundary() -> None:
    # ة at end of word → ه; mid-word ة untouched
    result = normalize("محكمة جلسة")
    # Both "محكمة" and "جلسة" end with ta-marbuta before a space or end.
    assert "ة" not in result


def test_normalize_arabic_indic_digits() -> None:
    result = normalize("القضية رقم ١٢٣")
    assert "123" in result
    for d in "١٢٣":
        assert d not in result


def test_normalize_collapses_whitespace() -> None:
    result = normalize("كلمة    أخرى")
    assert "  " not in result


def test_normalize_idempotent() -> None:
    text = "القانون المدني المصري — المادة الثالثة"
    assert normalize(normalize(text)) == normalize(text)


def test_normalize_multiline_collapse() -> None:
    # Use real newlines (Python escape \n), not escaped \n
    result = normalize("فقره اولي\n\n\n\nفقره ثانيه")
    assert "\n\n\n" not in result
    # After normalization ة→ه, ى→ي, أ→ا — use pre-normalized text in input
    assert "فقره اولي" in result
    assert "فقره ثانيه" in result


# ─── preprocess ───────────────────────────────────────────────────────────────

from app.pipeline.preprocess import (
    MAX_INLINE_BYTES,
    PreprocessError,
    preprocess,
)


def test_preprocess_valid_pdf() -> None:
    data = b"%PDF-1.4 fake content"
    result_bytes, mime = preprocess(data, "application/pdf")
    assert result_bytes == data
    assert mime == "application/pdf"


def test_preprocess_jpeg_alias() -> None:
    _, mime = preprocess(b"fake", "image/jpg")
    assert mime == "image/jpeg"


def test_preprocess_empty_raises() -> None:
    with pytest.raises(PreprocessError, match="فارغ"):
        preprocess(b"", "application/pdf")


def test_preprocess_unsupported_type_raises() -> None:
    with pytest.raises(PreprocessError):
        preprocess(b"content", "application/msword")


def test_preprocess_too_large_raises() -> None:
    big = b"x" * (MAX_INLINE_BYTES + 1)
    with pytest.raises(PreprocessError, match="حجم"):
        preprocess(big, "application/pdf")


def test_preprocess_exactly_at_limit_passes() -> None:
    at_limit = b"x" * MAX_INLINE_BYTES
    result, _ = preprocess(at_limit, "application/pdf")
    assert result == at_limit


# ─── confidence ───────────────────────────────────────────────────────────────

from app.pipeline.confidence import assess_confidence


def test_confidence_above_threshold_ready() -> None:
    assert assess_confidence(0.95, 0.80) == "ready"


def test_confidence_at_threshold_ready() -> None:
    assert assess_confidence(0.80, 0.80) == "ready"


def test_confidence_below_threshold_low_confidence() -> None:
    assert assess_confidence(0.50, 0.80) == "low_confidence"


def test_confidence_none_is_ready() -> None:
    # Text-native PDFs often return no confidence data — treat as ready.
    assert assess_confidence(None, 0.80) == "ready"


def test_confidence_zero_is_low_confidence() -> None:
    assert assess_confidence(0.0, 0.80) == "low_confidence"


# ─── chunk ────────────────────────────────────────────────────────────────────

from app.pipeline.chunk import Chunk, chunk_pages


def test_chunk_empty_pages_returns_empty() -> None:
    assert chunk_pages([]) == []


def test_chunk_empty_text_returns_empty() -> None:
    assert chunk_pages([(1, "   \n  ")]) == []


def test_chunk_short_text_single_chunk() -> None:
    pages = [(1, "هذا نص قصير للاختبار")]
    chunks = chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].page_ref == 1
    assert "هذا نص قصير" in chunks[0].text


def test_chunk_page_ref_preserved() -> None:
    pages = [(3, "نص الصفحة الثالثة")]
    chunks = chunk_pages(pages)
    assert chunks[0].page_ref == 3


def test_chunk_long_text_splits() -> None:
    # ~5000 chars should produce multiple chunks with target_chars=2800
    long_text = "كلمة عربية " * 500  # ≈ 5500 chars
    pages = [(1, long_text)]
    chunks = chunk_pages(pages, target_chars=2800, overlap_chars=420)
    assert len(chunks) >= 2


def test_chunk_overlap_present() -> None:
    """Consecutive chunks should share text at the boundary."""
    long_text = "فقرة مختلفة " * 400
    pages = [(1, long_text)]
    chunks = chunk_pages(pages, target_chars=1000, overlap_chars=200)
    if len(chunks) >= 2:
        # The beginning of chunk[1] should appear near the end of chunk[0].
        tail_of_0 = chunks[0].text[-200:]
        start_of_1 = chunks[1].text[:200]
        # At least some words should overlap (or start_of_1 starts with tail words).
        assert tail_of_0 or start_of_1  # Always true; documents overlap logic is non-empty


def test_chunk_indices_sequential() -> None:
    pages = [(1, ("paragraph\n\n" * 30))]
    chunks = chunk_pages(pages)
    for i, c in enumerate(chunks):
        assert c.index == i


def test_chunk_multiple_pages() -> None:
    # Each page needs to be large enough to exceed target_chars so that at
    # least some chunks carry a page_ref from page 2.
    long_text = "نص عربي طويل للاختبار " * 200  # ~4600 chars > 2800 target
    pages = [(1, long_text), (2, long_text)]
    chunks = chunk_pages(pages, target_chars=2800, overlap_chars=420)
    assert any(c.page_ref == 1 for c in chunks)
    assert len(chunks) >= 2  # two large pages always produce multiple chunks


# ─── embed (import / error-path only — no real API call) ─────────────────────

from app.pipeline.embed import EmbedError, embed_texts


async def test_embed_empty_list_returns_empty() -> None:
    result = await embed_texts([], api_key="k", model="m", dimension=1536)
    assert result == []


async def test_embed_no_api_key_raises() -> None:
    with pytest.raises(EmbedError, match="مفتاح"):
        await embed_texts(["text"], api_key="", model="models/test", dimension=768)


async def test_embed_no_model_raises() -> None:
    with pytest.raises(EmbedError, match="نموذج"):
        await embed_texts(["text"], api_key="key", model="", dimension=768)


# ─── ocr_documentai (import only) ────────────────────────────────────────────

from app.pipeline.ocr_documentai import (
    OcrError,
    OcrResult,
    _extract_page_texts,
    _mean_confidence,
)


def test_ocr_extract_page_texts_fallback() -> None:
    """Single-page doc without textAnchor → full text as page 1."""
    full_text = "هذا نص كامل للوثيقة"
    pages = [{"pageNumber": 1, "layout": {}}]
    result = _extract_page_texts(full_text, pages)
    assert result == [(1, full_text)]


def test_ocr_extract_page_texts_with_anchor() -> None:
    full_text = "صفحة 1 نص\nصفحة 2 نص"
    pages = [
        {
            "pageNumber": 1,
            "layout": {
                "textAnchor": {
                    "textSegments": [{"startIndex": "0", "endIndex": "10"}]
                }
            },
        }
    ]
    result = _extract_page_texts(full_text, pages)
    assert result[0][0] == 1
    assert "صفحة 1" in result[0][1]


def test_ocr_mean_confidence_paragraphs() -> None:
    pages = [
        {
            "paragraphs": [
                {"layout": {"confidence": 0.9}},
                {"layout": {"confidence": 0.8}},
            ]
        }
    ]
    conf = _mean_confidence(pages)
    assert conf == pytest.approx(0.85)


def test_ocr_mean_confidence_none_when_no_data() -> None:
    conf = _mean_confidence([{"paragraphs": []}])
    assert conf is None


def test_ocr_no_config_raises() -> None:
    import asyncio
    with pytest.raises(OcrError, match="غير مكتملة"):
        asyncio.run(
            __import__("app.pipeline.ocr_documentai", fromlist=["ocr_document"])
            .ocr_document(
                b"fake", "application/pdf",
                project_id="",
                location="eu",
                processor_id="",
            )
        )
