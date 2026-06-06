"""Conversational assistant generation flow (T085). [C-V][C-VIII][C-IX]

Component B used in the assistant path. Given a user question and the chunks the
**scoped retriever** already selected, it asks the LLM for a grounded Arabic
answer. It does NOT choose sources (that is the retriever) and does NOT store
anything (that is the API layer).

Invariants enforced by the prompt:
  [C-V]   every claim cites a provided "[مصدر N]"; nothing outside the chunks.
  [C-VIII] assistive posture — "tool, not legal advice; the lawyer decides".
  [C-IX]  any precedent/reference is framed persuasive-only (استئناس), never as
          binding authority or an outcome prediction.
"""

from __future__ import annotations

from app.llm.generate import build_prompt, generate
from app.retriever.retrieve import RetrievedChunk

ASSISTANT_INSTRUCTION = (
    "أجب عن سؤال المستخدم بالاعتماد الحصري على المقاطع المصدرية أعلاه. "
    "ضع مرجع المصدر [مصدر N] بعد كل معلومة. "
    "إن لم تكن الإجابة موجودة في المقاطع، فاذكر ذلك صراحةً ولا تخمّن. "
    "أي إشارة إلى سابقة أو مرجع قانوني هي للاستئناس فقط وليست مُلزِمة ولا تنبؤًا "
    "بنتيجة. تذكّر أن هذا النظام أداة مساعدة وليس استشارة قانونية، والقرار للمحامي "
    "المختص."
)


async def answer_query(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    api_key: str,
    model: str,
) -> str:
    """Return a grounded Arabic answer for *query* over the retrieved *chunks*."""
    context_texts = [c.chunk_text for c in chunks]
    task = f"{ASSISTANT_INSTRUCTION}\n\nالسؤال: {query}"
    prompt = build_prompt(task, context_texts)
    return await generate(prompt, api_key=api_key, model=model, temperature=0.2)
