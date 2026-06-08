"""Multi-provider LLM dispatch — Component B extension (spec 002, FR-141 / R1).

GENERATION ONLY.  Same posture as :mod:`app.llm.generate`: this module never
retrieves, never schedules, never stores.  It adds a per-firm provider switch
on top of the existing Gemini client:

  * ``firm_settings.llm_provider_config`` = ``{"provider": ..., "model": ...}``
  * ``firm_settings.llm_api_key``          = the secret key (unchanged column,
    audit-redacted [C-III])

Provider "gemini" goes through the proven direct client in ``generate.py``.
Any other provider (openai, anthropic, ...) is dispatched through LiteLLM
with model id ``"<provider>/<model>"`` — switching providers is a Settings
change only, no code change.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.llm.generate import LlmError, generate

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "gemini",
    "model": "models/gemini-2.0-flash",
}

SUPPORTED_PROVIDERS = ("gemini", "openai", "anthropic", "mistral", "groq")


def parse_provider_config(raw: Any) -> dict[str, Any]:
    """Normalise ``firm_settings.llm_provider_config`` (jsonb dict or string)."""
    cfg: dict[str, Any] = {}
    if isinstance(raw, str):
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = {}
    elif isinstance(raw, dict):
        cfg = raw
    merged = {**_DEFAULT_CONFIG, **{k: v for k, v in cfg.items() if v}}
    return merged


async def dispatch(
    prompt: str,
    *,
    api_key: str,
    provider_config: Any = None,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
    timeout: float = 120.0,
) -> str:
    """Send *prompt* to the firm-configured LLM provider and return raw text.

    Raises:
        LlmError: missing key, unknown provider, or provider call failure.
    """
    cfg = parse_provider_config(provider_config)
    provider: str = str(cfg["provider"]).lower()
    model: str = str(cfg["model"])

    if not api_key:
        raise LlmError(
            "مفتاح الذكاء الاصطناعي غير مضبوط — أدخله في إعدادات المكتب"
        )
    if provider not in SUPPORTED_PROVIDERS:
        raise LlmError(f"مزوّد الذكاء الاصطناعي غير مدعوم: {provider}")

    if provider == "gemini":
        # Keep the direct, battle-tested Gemini path (no extra hop).
        return await generate(
            prompt,
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            timeout=timeout,
        )

    return await _dispatch_litellm(
        prompt,
        provider=provider,
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        timeout=timeout,
    )


async def _dispatch_litellm(
    prompt: str,
    *,
    provider: str,
    model: str,
    api_key: str,
    temperature: float,
    max_output_tokens: int,
    timeout: float,
) -> str:
    try:
        import litellm  # imported lazily; only needed for non-Gemini providers
    except ImportError as exc:  # pragma: no cover - deployment misconfig
        raise LlmError(
            "حزمة litellm غير مثبَّتة — لا يمكن استخدام مزوّد غير Gemini"
        ) from exc

    model_id = model if "/" in model else f"{provider}/{model}"
    try:
        resp = await asyncio.wait_for(
            litellm.acompletion(
                model=model_id,
                api_key=api_key,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_output_tokens,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        raise LlmError("انتهت مهلة طلب الذكاء الاصطناعي") from exc
    except Exception as exc:
        # Never include the API key in the message [C-III].
        raise LlmError(f"طلب الذكاء الاصطناعي فشل ({provider}): {exc}") from exc

    try:
        text = (resp.choices[0].message.content or "").strip()
    except (AttributeError, IndexError) as exc:
        raise LlmError("استجابة غير متوقعة من مزوّد الذكاء الاصطناعي") from exc
    if not text:
        raise LlmError("استجابة فارغة من نموذج الذكاء الاصطناعي")

    logger.debug(
        "llm dispatch: provider=%s model=%s prompt_chars=%d response_chars=%d",
        provider, model_id, len(prompt), len(text),
    )
    return text


async def load_llm_context(conn) -> tuple[str, dict[str, Any]]:
    """Fetch (api_key, provider_config) from firm_settings in one query."""
    row = await conn.fetchrow(
        "SELECT llm_api_key, llm_provider_config FROM firm_settings LIMIT 1"
    )
    if row is None:
        raise LlmError("إعدادات المكتب غير مُهيَّأة")
    return (row["llm_api_key"] or ""), parse_provider_config(
        row["llm_provider_config"]
    )
