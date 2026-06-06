"""LLM generation client — Component B (T054).

GENERATION ONLY.  This module sends retrieved context + a task prompt to the
LLM (via the firm's API key) and returns the raw generated text.  It DOES NOT:
  * decide which documents to read (that is the Retriever, Component A),
  * decide when to send reminders or reports (that is the Scheduler, Component C),
  * store any output in the DB (the caller in ai_outputs.py does that).

Architecture invariant (plan.md, constitution [C-IV]):
  * Reminders/reports NEVER go through this function.
  * Only the conversational assistant and analysis features (phases 4+) may
    use agentic invocations; summarize/extract are single-shot.

Model
-----
Google Generative AI REST API (the same API key used for embeddings — the firm
provides one key for both).  Default model from ``firm_settings.llm_api_key``
with model name read from a separate ``llm_config`` field or defaulting to the
research recommendation.  The model is ONLY called for generation.

Prompt design for legal Arabic
-------------------------------
All prompts:
  1. Prefix with the «assistive tool, not legal advice» posture.  [C-VIII]
  2. Instruct the model to ground every claim with "[مصدر N]" citations that
     map to the retrieved chunks passed in the context.  [C-V]
  3. For reference/precedent outputs: include the persuasive-only disclaimer.  [C-IX]
  4. Return structured JSON so the caller can parse claims + source mappings.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GENAI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "models/gemini-2.5-flash-preview-05-20"

# System-level posture injected into every prompt.  [C-VIII]
_POSTURE_PREFIX = (
    "أنت مساعد قانوني. هذا النظام أداة مساعدة وليس استشارة قانونية. "
    "المسؤولية المهنية تقع على عاتق المحامي المختص. "
    "استند في كل ادعاء إلى المقاطع المصدرية المقدَّمة فقط. "
    "إذا لم تجد إجابة في المقاطع المقدَّمة، قل ذلك صراحةً.\n\n"
)


class LlmError(Exception):
    """Raised when the LLM call fails (API error, quota, bad response)."""


async def generate(
    prompt: str,
    *,
    api_key: str,
    model: str = _DEFAULT_MODEL,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
    timeout: float = 120.0,
) -> str:
    """Send *prompt* to the LLM and return the generated text.

    Args:
        prompt:            Full prompt (already includes context chunks and
                           task instruction).  Should include the posture prefix
                           via :func:`build_prompt`.
        api_key:           Firm's Google API key (from ``firm_settings.llm_api_key``).
        model:             Model name, e.g. ``"models/gemini-2.0-flash"``.
        temperature:       Sampling temperature (low = more deterministic).
        max_output_tokens: Limit on output length.
        timeout:           HTTP timeout in seconds.

    Returns:
        The model's raw text response.

    Raises:
        LlmError: On API errors or empty responses.
    """
    if not api_key:
        raise LlmError(
            "مفتاح الذكاء الاصطناعي غير مضبوط — أدخله في إعدادات المكتب"
        )

    model_id = model.removeprefix("models/")
    url = f"{_GENAI_BASE}/models/{model_id}:generateContent"

    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "text/plain",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": api_key},
                json=body,
            )
    except httpx.HTTPError as exc:
        raise LlmError(f"طلب الذكاء الاصطناعي فشل (شبكة): {exc}") from exc

    if resp.status_code != 200:
        raise LlmError(
            f"واجهة برمجة الذكاء الاصطناعي أعادت خطأ "
            f"{resp.status_code}: {resp.text[:400]}"
        )

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise LlmError("استجابة فارغة من نموذج الذكاء الاصطناعي")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise LlmError("استجابة فارغة من نموذج الذكاء الاصطناعي")

    logger.debug(
        "llm: model=%s prompt_chars=%d response_chars=%d",
        model, len(prompt), len(text),
    )
    return text


# ── prompt builders ───────────────────────────────────────────────────────────


def build_prompt(task_instruction: str, context_chunks: list[str]) -> str:
    """Assemble a grounded prompt with posture prefix and numbered context chunks.

    The model is instructed to cite "[مصدر N]" for every claim.  The caller
    maps N back to the retrieved chunks to build ``source_links``.  [C-V]
    """
    context_section = "\n\n".join(
        f"[مصدر {i + 1}]\n{text}" for i, text in enumerate(context_chunks)
    )
    return (
        f"{_POSTURE_PREFIX}"
        f"=== المقاطع المصدرية ===\n{context_section}\n\n"
        f"=== المهمة ===\n{task_instruction}"
    )


SUMMARIZE_INSTRUCTION = """
اكتب ملخصاً قانونياً موجزاً للوثيقة المقدَّمة مستنداً حصراً إلى المقاطع أعلاه.
بعد الملخص، استخرج النقاط الرئيسية في JSON بالشكل التالي:
{
  "ملخص": "...",
  "الأطراف": ["..."],
  "التواريخ": ["..."],
  "المطالبات": ["..."],
  "المبالغ": ["..."],
  "النقاط_الرئيسية": ["..."]
}
ضع مرجع المصدر [مصدر N] بعد كل بيان مستخرج.
لا تضف معلومات خارج المقاطع المقدَّمة.
""".strip()
