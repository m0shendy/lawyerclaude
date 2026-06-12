"""Risk-signal detection (T096). [C-VIII][C-IX]

Component B used by the risk-signals feature. Surfaces *signals worth a lawyer's
attention* found in the document's own text (e.g. short notice periods,
one-sided penalty clauses, ambiguous obligations) — grounded in the sources,
each cited. It explicitly does NOT predict outcomes and is not legal advice; the
posture is carried in the prompt and surfaced again in the UI. [C-VIII][C-IX]

Selects nothing autonomously, stores nothing — the caller persists each signal
as a ``draft_unreviewed`` ``risk_signal`` output behind the review gate. [C-II]
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.generate import build_prompt, generate
from app.retriever.retrieve import RetrievedChunk

_RISK_INSTRUCTION = (
    "استخرج «إشارات» تستحق انتباه المحامي من نص المستند أعلاه فقط (مثل: مهل قصيرة، "
    "شروط جزائية أحادية، التزامات غامضة، تنازلات واسعة، غياب ضمانات). "
    "ضع [مصدر N] بعد كل إشارة. "
    "لا تتنبأ بأي نتيجة أو حكم، ولا تقدّم نصيحة قانونية — هذه أداة مساعدة لتنبيه "
    "المحامي فقط، والتقدير النهائي له.\n\n"
    "أعد النتيجة بصيغة JSON بالشكل:\n"
    '{\n'
    '  "إشارات": [\n'
    '    {"الوصف": "... [مصدر N]", "الخطورة": "منخفضة|متوسطة|مرتفعة"}\n'
    "  ],\n"
    '  "تنويه": "هذه إشارات للمراجعة وليست تنبؤاً بنتيجة"\n'
    "}"
)


async def detect_risk_signals(
    chunks: list[RetrievedChunk], *, api_key: str, model: str
) -> dict[str, Any]:
    """Return a grounded risk-signal dict for the document *chunks*."""
    context_texts = [c.chunk_text for c in chunks]
    prompt = build_prompt(_RISK_INSTRUCTION, context_texts)
    raw = await generate(prompt, api_key=api_key, model=model, temperature=0.1)
    return _parse(raw, len(context_texts))


def _parse(raw: str, context_count: int) -> dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            parsed = json.loads(match.group())
            parsed["raw_text"] = raw
            parsed["context_count"] = context_count
            return parsed
        except json.JSONDecodeError:
            pass
    return {"raw_text": raw, "context_count": context_count}
