"""Contract analysis generation (T089, T090). [C-V][C-VIII]

Component B used by the contract-analysis feature. Given a contract's retrieved
chunks, it asks the LLM to (a) identify which standard clauses are present, (b)
flag missing/unusual clauses against a simple playbook, all grounded in the
provided sources. It selects nothing on its own and stores nothing — the caller
(ai_outputs.py) persists every finding as a ``draft_unreviewed`` output. [C-II]

The clause taxonomy is a *checklist*, not legal advice: the model only reports
which items it can/can't find in the sources, with citations. Posture and
persuasive-only framing come from ``generate.build_prompt``'s posture prefix.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.generate import build_prompt, generate
from app.retriever.retrieve import RetrievedChunk

# A pragmatic playbook of clauses commonly expected in commercial contracts
# (Egyptian civil-law context). This is a review *checklist*, not a rule of law —
# the model reports presence/absence grounded in the document only.
CLAUSE_TAXONOMY: list[str] = [
    "الأطراف والصفة",
    "محل العقد ونطاقه",
    "المقابل المالي وطريقة السداد",
    "المدة والتجديد",
    "الالتزامات والتعهدات",
    "الضمانات",
    "الإنهاء والفسخ",
    "الشرط الجزائي والتعويض",
    "القوة القاهرة",
    "السرية",
    "القانون الواجب التطبيق",
    "تسوية المنازعات والاختصاص",
    "الإخطارات",
    "التنازل",
]

_ANALYSIS_INSTRUCTION = (
    "أنت تراجع عقداً بالاعتماد الحصري على المقاطع المصدرية أعلاه. "
    "لكل بند من قائمة البنود القياسية التالية، حدّد ما إذا كان موجوداً في المقاطع "
    "(مع وضع [مصدر N]) أم غير موجود. ثم أبرِز البنود الناقصة أو غير المعتادة. "
    "لا تستنتج بنوداً غير واردة في المقاطع، ولا تقدّم رأياً قانونياً نهائياً — هذه "
    "مراجعة مساعِدة فقط.\n\n"
    "قائمة البنود القياسية:\n"
    + "\n".join(f"- {c}" for c in CLAUSE_TAXONOMY)
    + "\n\nأعد النتيجة بصيغة JSON بالشكل:\n"
    '{\n'
    '  "البنود_الموجودة": ["اسم البند [مصدر N]"],\n'
    '  "البنود_الناقصة": ["اسم البند"],\n'
    '  "البنود_غير_المعتادة": ["وصف موجز [مصدر N]"],\n'
    '  "ملاحظات": "..."\n'
    "}"
)


async def analyze_contract(
    chunks: list[RetrievedChunk], *, api_key: str, model: str
) -> dict[str, Any]:
    """Return a grounded clause analysis dict for the contract *chunks*."""
    context_texts = [c.chunk_text for c in chunks]
    prompt = build_prompt(_ANALYSIS_INSTRUCTION, context_texts)
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
