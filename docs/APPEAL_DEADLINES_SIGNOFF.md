# Appeal-Deadline Calculation — Expert Sign-Off Gate (T081) [C-X]

**Status: OFF — NOT YET BLESSED. Do not enable in any firm.**

Constitution Principle X requires that appeal-deadline suggestions are
**confirm-required, behind a feature flag, and off until expert sign-off**. This
document records that gate and what must happen before it can open.

## Why this is gated

Appeal periods (استئناف / معارضة / نقض) are legal facts with serious consequences
if wrong — a miscalculated deadline can forfeit a client's right to appeal.
Shipping unverified day-counts, *even behind a flag*, risks them later being
treated as authoritative. Therefore the system ships **inert**:

1. **No periods are hard-coded.** `backend/app/scheduler/appeal_deadlines.py`
   defines `APPEAL_PERIODS_DAYS = {}` (empty). With it empty,
   `suggest_appeal_deadlines()` returns `[]` and the generation endpoint creates
   nothing. (Guarded by `tests/test_phase10_features.py`.)
2. **The feature flag defaults OFF.** `firm_settings.feature_appeal_deadlines`
   defaults `false`; `backend/app/core/flags.py` `require_flag` returns 403 while
   off. Both the generation and confirm endpoints enforce it.
3. **Suggestions never notify.** Even once created, appeal rows are
   `confirmed = false`; the deterministic scheduler only fires on
   `confirmed = true` deadlines, so a suggestion is silent until the responsible
   lawyer explicitly confirms it. [C-X][C-IV]

## What must happen before enabling (the sign-off checklist)

- [ ] A qualified Egyptian-law practitioner reviews and **signs off in writing**
      on the appeal periods and their counting rules (start point, calendar vs.
      working days, holidays, service-of-judgment nuances) per appeal type.
- [ ] Record the sign-off here: name, bar registration, date, and the exact
      periods agreed.
- [ ] Populate `APPEAL_PERIODS_DAYS` with the blessed values **only**.
- [ ] Add/extend tests asserting the blessed periods and counting behaviour.
- [ ] Confirm the ToS note (below) is surfaced to the firm.
- [ ] Enable `feature_appeal_deadlines` per-firm **only after** the above.

## ToS / UI note (must remain true while the feature exists) [C-VIII]

> حساب مواعيد الطعن هو مسؤولية المحامي المختص. المقترحات الآلية للمراجعة والتأكيد
> فقط، وليست بديلاً عن تقدير المحامي، ولا يُعتدّ بها إلا بعد التحقق والتأكيد.

(Deadline calculation is the responsible lawyer's duty. Automated suggestions are
for review and confirmation only — never a substitute for the lawyer's judgment,
and have no effect until verified and confirmed.)

## Sign-off record

_None yet. The feature remains OFF._
