"""Embedding client (T049). [R1]

Generates dense vector embeddings for chunk texts using the Google Generative
AI REST API.  The model, dimension, and API key come from the per-firm
``firm_settings`` row:

  * ``embedding_config.model``     — e.g. "models/gemini-embedding-exp-03-07"
  * ``embedding_config.dimension`` — e.g. 1536 (must match the DB vector column)
  * ``llm_api_key``                — the firm's Google API key (client-provided)

Batch semantics
---------------
Google's ``batchEmbedContents`` endpoint handles up to 100 texts per request.
Larger lists are split into batches automatically.

The returned vectors are validated against the expected dimension so a
misconfigured model is caught before any DB write.

Tuning at the Phase-1 checkpoint
---------------------------------
The choice of embedding model and dimension affects retrieval quality.  After
validating OCR confidence on real scans (T052 checkpoint), also validate that
the chosen model:
  1. Produces acceptable Arabic recall (test a few legal queries).
  2. Produces vectors of exactly ``embedding_config.dimension`` floats.
  3. Stays within the Google API rate/quota limits for the firm's key.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Google Generative AI REST base URL.
_GENAI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Google's batchEmbedContents limit per request.
_BATCH_SIZE = 100


class EmbedError(Exception):
    """Raised when embedding fails (API error, quota, misconfiguration)."""


async def embed_texts(
    texts: list[str],
    *,
    api_key: str,
    model: str,
    dimension: int,
    task_type: str = "RETRIEVAL_DOCUMENT",
    timeout: float = 120.0,
) -> list[list[float]]:
    """Embed *texts* using the Google Generative AI API.

    Args:
        texts:      List of normalized Arabic texts to embed.
        api_key:    Google API key (from ``firm_settings.llm_api_key``).
        model:      Model resource name (from ``firm_settings.embedding_config.model``),
                    e.g. ``"models/gemini-embedding-exp-03-07"``.
        dimension:  Expected output dimension (from ``embedding_config.dimension``).
                    Passed as ``outputDimensionality`` so the model truncates/projects
                    to exactly this size.  Must match the DB ``vector(N)`` column.
        task_type:  Embedding task type; ``"RETRIEVAL_DOCUMENT"`` for document chunks,
                    ``"RETRIEVAL_QUERY"`` for query vectors.
        timeout:    HTTP timeout in seconds per batch request.

    Returns:
        A list of float vectors, one per input text, in the same order.

    Raises:
        EmbedError: On API errors, empty responses, or dimension mismatches.
    """
    if not texts:
        return []
    if not api_key:
        raise EmbedError(
            "مفتاح واجهة برمجة التطبيقات غير مضبوط — "
            "أدخل مفتاح الذكاء الاصطناعي في إعدادات المكتب"
        )
    if not model:
        raise EmbedError(
            "نموذج التضمين غير محدد في إعدادات التضمين (embedding_config.model)"
        )

    embeddings: list[list[float]] = []
    url = f"{_GENAI_BASE}/models/{model.removeprefix('models/')}:batchEmbedContents"

    async with httpx.AsyncClient(timeout=timeout) as client:
        for batch_start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[batch_start : batch_start + _BATCH_SIZE]
            requests_payload: list[dict[str, Any]] = [
                {
                    "model": model if model.startswith("models/") else f"models/{model}",
                    "content": {"parts": [{"text": t}]},
                    "taskType": task_type,
                    "outputDimensionality": dimension,
                }
                for t in batch
            ]
            body = {"requests": requests_payload}
            try:
                # Send the key as a header, NOT a ?key= query param: httpx logs
                # request URLs at INFO, which would leak the secret into worker
                # logs. The header keeps it out of the URL. [C-III]
                resp = await client.post(
                    url,
                    headers={"x-goog-api-key": api_key},
                    json=body,
                )
            except httpx.HTTPError as exc:
                raise EmbedError(f"طلب التضمين فشل (شبكة): {exc}") from exc

            if resp.status_code != 200:
                raise EmbedError(
                    f"واجهة برمجة تطبيقات التضمين أعادت خطأ "
                    f"{resp.status_code}: {resp.text[:400]}"
                )

            data = resp.json()
            batch_embeddings: list[dict] = data.get("embeddings", [])
            if len(batch_embeddings) != len(batch):
                raise EmbedError(
                    f"عدد نواتج التضمين ({len(batch_embeddings)}) "
                    f"لا يطابق عدد المدخلات ({len(batch)})"
                )

            for item in batch_embeddings:
                vec: list[float] = item.get("values", [])
                if len(vec) != dimension:
                    raise EmbedError(
                        f"بُعد ناقل التضمين ({len(vec)}) "
                        f"لا يطابق الإعداد ({dimension}). "
                        f"تحقق من توافق النموذج مع بُعد المتجهات."
                    )
                embeddings.append(vec)

            logger.debug(
                "embed batch %d–%d/%d ok",
                batch_start,
                batch_start + len(batch) - 1,
                len(texts),
            )

    return embeddings
