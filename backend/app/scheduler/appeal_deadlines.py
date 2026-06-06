"""Appeal-deadline suggestion generation — SCAFFOLD ONLY (T077). [C-X]

⚠️  EXPERT SIGN-OFF REQUIRED — READ BEFORE POPULATING.

Deterministic generator (Component C — no LLM) that would propose appeal-type
deadlines as **suggestions** (``confirmed=false``) derived from a judgment date.
Per the constitution (Principle X) and the build plan (T081), appeal-deadline
calculation is **off until an expert Egyptian-law practitioner signs off** on the
periods and rules. Therefore:

  * ``APPEAL_PERIODS_DAYS`` is intentionally **EMPTY**. No statutory periods are
    hard-coded here, because shipping unverified legal day-counts — even behind a
    feature flag — risks them later being treated as fact. They must be supplied
    and blessed by a qualified lawyer.
  * With the table empty, ``suggest_appeal_deadlines`` returns ``[]`` — the
    mechanism is inert. The feature flag (``feature_appeal_deadlines``) is a
    second gate and also defaults OFF.

When (and only when) an expert has signed off, populate ``APPEAL_PERIODS_DAYS``
with the agreed periods, record the sign-off per T081, and enable the flag.

Suggestions are never treated as fact and never trigger notifications: the
scheduler only ever fires on ``confirmed = true`` deadlines, so a suggestion is
silent until the responsible lawyer confirms it. [C-X][C-IV]
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

# Appeal type → statutory period in days from the judgment date.
# EMPTY BY DESIGN — populate ONLY after expert sign-off (see module docstring). [C-X]
APPEAL_PERIODS_DAYS: dict[str, int] = {}

# Human labels for the appeal types (used in suggestion titles).
_APPEAL_TYPE_LABELS = {
    "appeal_istinaf": "ميعاد استئناف",
    "mu_arada": "ميعاد معارضة",
    "naqd": "ميعاد نقض",
}


def suggest_appeal_deadlines(
    judgment_date: date,
    *,
    responsible_user_id: UUID,
    derived_from_document_id: UUID | None = None,
    low_confidence_flag: bool = False,
) -> list[dict[str, Any]]:
    """Return appeal-deadline *suggestions* (``confirmed=false``) for a judgment.

    Each suggestion is a dict ready to insert into ``deadlines``. Returns ``[]``
    while ``APPEAL_PERIODS_DAYS`` is empty (the default, pending expert sign-off).
    The caller persists these as inert suggestions; they never notify until the
    responsible lawyer confirms. [C-X]
    """
    suggestions: list[dict[str, Any]] = []
    for appeal_type, period_days in APPEAL_PERIODS_DAYS.items():
        suggested = judgment_date + timedelta(days=period_days)
        label = _APPEAL_TYPE_LABELS.get(appeal_type, appeal_type)
        suggestions.append(
            {
                "type": appeal_type,
                "title": f"{label} (مقترح — يتطلب تأكيد المحامي)",
                "basis": (
                    f"مقترح آلياً: تاريخ الحكم {judgment_date.isoformat()} + "
                    f"{period_days} يوماً. غير مؤكَّد — للتحقق والتأكيد فقط."
                ),
                "due_date": suggested,
                "suggested_date": suggested,
                "confirmed": False,
                "responsible_user_id": responsible_user_id,
                "derived_from_document_id": derived_from_document_id,
                "low_confidence_flag": low_confidence_flag,
            }
        )
    return suggestions
