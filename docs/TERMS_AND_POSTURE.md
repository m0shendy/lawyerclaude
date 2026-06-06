# Assistive-Tool Posture & Terms Copy (T099) [C-VIII][C-IX]

Single source for the "assistive tool, not legal advice" copy that must appear
across the UI, AI responses, and the firm Terms of Service. Principle VIII
(assistive posture) and IX (persuasive-only references) require this everywhere
AI output is shown or sent.

## Where it already appears

| Surface | Copy | Location |
|---|---|---|
| Persistent UI banner | «أداة مساعدة — ليست استشارة قانونية. تبقى المسؤولية المهنية والتقدير القانوني على المحامي» | `frontend/components/Disclaimer.tsx` (root layout) |
| AI prompts (every generation) | posture prefix injected into every prompt | `backend/app/llm/generate.py` `_POSTURE_PREFIX` |
| AI-marked outputs | draft_unreviewed banner + source links until approved | `frontend/components/AiMarkedOutput.tsx` |
| Assistant screen | assistive + persuasive-only note above the chat | `frontend/app/assistant/page.tsx` |
| Reference search | persuasive-only / not-binding / not-prediction notice | `frontend/app/references/page.tsx`, `backend/app/retriever/references.py` `PERSUASIVE_ONLY_NOTICE` |
| Risk signals | "إشارات للمراجعة وليست تنبؤاً بنتيجة" | `backend/app/llm/risk_signals.py` |
| Appeal deadlines | lawyer-responsibility note | `docs/APPEAL_DEADLINES_SIGNOFF.md` |

## Canonical Terms-of-Service clauses (Arabic)

1. **طبيعة الأداة:** هذا النظام أداة مساعدة للعمل المكتبي ولا يُقدّم استشارة قانونية.
   المسؤولية المهنية والتقدير القانوني النهائي يقعان على عاتق المحامي المختص.
2. **مخرجات الذكاء الاصطناعي:** كل مخرج آلي يُنشأ كمسودة غير معتمدة، مرتبط بمصادره،
   ولا يجوز تصديره أو إرساله رسمياً قبل اعتماد المحامي المكلَّف أو الشريك/المدير.
3. **المراجع والسوابق:** تُعرض للاستئناس فقط؛ غير مُلزِمة ولا تُعدّ تنبؤاً بنتيجة.
4. **المواعيد والطعون:** حساب المواعيد — وخاصة مواعيد الطعن — مسؤولية المحامي؛
   المقترحات الآلية للمراجعة والتأكيد فقط.
5. **الخصوصية والعزل:** بيانات كل مكتب معزولة فعلياً؛ لا تدخل بيانات المكاتب في أي
   مجموعة مشتركة، والمجموعة القانونية المشتركة قانون عام للقراءة فقط.

These clauses must be presented to each firm at onboarding and kept in sync with
the UI copy above.
