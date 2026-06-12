# Tasks: SaaS Platform Admin Console

**Feature Directory**: `specs/003-platform-admin-console`
**Input**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md),
[contracts/ui-screens.md](contracts/ui-screens.md), [quickstart.md](quickstart.md)

**Convention**: backend `backend/app/…`, frontend `frontend/app/…`, migrations
`supabase/migrations/…`. Tests included where the spec mandates them (FR-313 isolation
suite is a release gate; US1 security behaviors are test-required).

---

## Phase 1: Setup

**Purpose**: Skeletons so every later task has a home. No behavior yet.

- [x] T001 Create `backend/app/api/admin.py` router skeleton (prefix `/admin`, empty routes) and register it in `backend/app/main.py`
- [x] T002 [P] Create `frontend/app/admin/layout.tsx` operator shell skeleton (own minimal RTL nav: لوحة المكاتب / الفوترة / سجل التدقيق / الحالة التشغيلية; no firm AppNav import) and `frontend/lib/adminApi.ts` fetch wrapper (operator token storage, 401 → redirect `/admin/login`)
- [x] T003 [P] Verify no firm-facing component links into `/admin/**` (grep `frontend/components/AppNav.tsx` and sitemap/nav components; add nothing — assert only)

**Checkpoint**: App builds; `/admin` renders an empty shell; `GET /admin/me` returns 401.

---

## Phase 2: Foundational (blocking all user stories)

**Purpose**: Schema + the fail-closed authorization chain every story depends on.

- [x] T004 Write migration `supabase/migrations/0030_platform_admin.sql` per [data-model.md](data-model.md): `platform_operators`, `operator_sessions`, `operator_login_attempts`, `manual_payments`, `billing_event_resolutions`, `worker_heartbeats`, `admin_firm_usage` view; audit triggers via `attach_audit_trigger` on the five accountable tables (NOT `worker_heartbeats`); **zero grants to `app_user`** (service context only). Verify `admin_firm_usage` column references against live schema (`documents.file_size`, `audit_log.at`) before finalizing
- [x] T005 Apply migration 0030 to the Supabase project and verify: tables exist, `select * from admin_firm_usage` works on the postgres connection, `app_user` gets `permission denied` on `platform_operators`
- [x] T006 Implement `backend/app/core/operator.py` — `require_operator` FastAPI dependency: verify ES256 JWT (reuse `_decode_token` from `core/security.py`) → require `aal == "aal2"` claim → active `platform_operators` row → `operator_sessions` row with `last_seen` < 30 min (touch on success, purge + 401 on stale) → return operator context. Any failure ⇒ 401/403 with empty body (FR-312); firm-role tokens ⇒ 403 + audit row (FR-303)
- [x] T007 Implement service-connection helper for admin handlers in `backend/app/core/operator.py`: acquire `SERVICE_DATABASE_URL` connection and SET GUCs `app.user_id`=<operator id>, `app.user_role='platform_operator'`, `app.context='platform_admin'`; plus `audit_admin_read(conn, entity, record_id, firm_id)` helper that INSERTs an `admin_read` audit row (FR-311)
- [x] T008 [P] Add pydantic models for admin payloads in `backend/app/models/admin.py` (login, mfa, lifecycle actions, manual payment, resolution, responses per [contracts/rest-api.md](contracts/rest-api.md)) and export from `backend/app/models/__init__.py`

**Checkpoint**: `require_operator` rejects everything (no operators exist yet) — fail-closed proven before any feature ships.

---

## Phase 3: User Story 1 — Secure Operator Login (P1) 🎯 MVP

**Goal**: Dedicated operator entry point: proxied login + TOTP + lockout + idle sessions + revocation, every attempt audit-logged.

**Independent test**: quickstart §1 — valid operator+MFA succeeds; every firm role 403; 5 bad passwords → locked; idle 31 min → re-auth.

- [x] T009 [US1] Implement `POST /admin/login` in `backend/app/api/admin.py`: lockout check against `operator_login_attempts` (≥5 fails / 15 min / no intervening success ⇒ 423 with retry-after), server-side GoTrue password grant (`{SUPABASE_URL}/auth/v1/token?grant_type=password` with anon key), record attempt row + audit row for success AND failure, return `{mfa_required, factor_id, challenge_token}` (list TOTP factors via GoTrue; if none enrolled return `{mfa_enrollment_required}`)
- [x] T010 [US1] Implement `POST /admin/mfa/enroll` + `POST /admin/mfa/verify` in `backend/app/api/admin.py`: enroll TOTP factor / challenge+verify via GoTrue MFA API to obtain aal2 token; on verified: require active `platform_operators` row (else 403 + audit), INSERT `operator_sessions`, audit row, return `{access_token, expires_in}`
- [x] T011 [US1] Implement `POST /admin/logout` (delete own session row + audit), `GET /admin/me` (operator id, display name, session created), `POST /admin/sessions/revoke-all` (delete ALL operator sessions + audit) in `backend/app/api/admin.py`
- [x] T012 [P] [US1] Build `frontend/app/admin/login/page.tsx`: step 1 email+password → step 2 TOTP code (or first-time enrollment QR); errors for bad credentials, lockout (show remaining time from 423), bad code; on success store token via `adminApi` and route to `/admin`
- [x] T013 [US1] Wire the operator session guard into `frontend/app/admin/layout.tsx`: on mount call `/admin/me`; 401 → redirect `/admin/login` with "انتهت الجلسة" notice; render operator display name + logout button
- [x] T014 [US1] Write `backend/tests/test_admin_auth.py`: lockout after 5 failures, success resets window, firm-role token → 403 on `/admin/me`, aal1 token → 401, stale session (force `last_seen` −31 min) → 401, revoke-all kills a live session

**Checkpoint**: US1 fully demonstrable per quickstart §1. MVP deliverable.

---

## Phase 4: User Story 2 — All-Firms Dashboard (P1)

**Goal**: Situational awareness: every firm with status/plan/trial/usage counts + attention flags; metadata only.

**Independent test**: quickstart §2 — two seeded firms listed correctly; trial ≤3 d flagged; zero work-product fields; detail read audit-logged.

- [x] T015 [US2] Implement `GET /admin/firms` in `backend/app/api/admin.py`: list firms joined to latest subscription + `admin_firm_usage` counts; filters `status`, `plan`, `q` (name/slug ilike), pagination; compute `attention_flags` (`trial_expiring` ≤3 d, `payment_failed` = subscription past_due, `unprocessed_event` = unresolved unprocessed billing_events hint)
- [x] T016 [US2] Implement `GET /admin/firms/{id}` in `backend/app/api/admin.py`: firm + subscription + usage from `admin_firm_usage` ONLY (counts, storage bytes, last activity); call `audit_admin_read()` per request (FR-311); response schema contains no work-product fields (FR-310)
- [x] T017 [P] [US2] Build `frontend/app/admin/page.tsx` dashboard: firms table (name, slug, status badge, plan, trial expiry, user/case/doc counts), attention strip on top, search box + status/plan filter chips, row click → `/admin/firms/[id]`
- [x] T018 [US2] Build `frontend/app/admin/firms/[id]/page.tsx` detail view (read-only this phase): firm card, usage counts panel, subscription panel — action buttons land in US3

**Checkpoint**: Dashboard usable end-to-end with real firms; isolation posture intact.

---

## Phase 5: User Story 3 — Firm Lifecycle Management (P1)

**Goal**: Suspend / reactivate / cancel / extend trial / change plan — confirmed, prompt, audit-logged old→new.

**Independent test**: quickstart §3 — suspend blocks staff + scheduler skips; reactivate restores; extend-trial on cancelled firm rejected; all audit rows present.

- [x] T019 [US3] Implement lifecycle endpoints in `backend/app/api/admin.py`: `POST /admin/firms/{id}/suspend|reactivate|cancel` (UPDATE `firms.status` via service conn with operator GUCs so the audit trigger records old→new; 409 on no-op same-state), `POST /admin/firms/{id}/extend-trial` (`days` 1–90; 422 if firm cancelled per FR-321), `POST /admin/firms/{id}/change-plan` (UPDATE subscription plan only — moves no money, FR-322); all require `{confirm: true}` else 422
- [x] T020 [US3] Verify suspension propagation: confirm the existing firm-status middleware returns the suspension response on the firm's next request and `scheduler_worker` skips suspended firms (read `backend/app/core/` + `backend/workers/scheduler_worker.py`; fix the gap if either does not check `firms.status`)
- [x] T021 [US3] Add lifecycle actions to `frontend/app/admin/firms/[id]/page.tsx`: five buttons, each behind a confirm dialog naming the firm + exact consequence + checkbox before enable (per [contracts/ui-screens.md](contracts/ui-screens.md)); dismiss = no-op; success toast includes "تم تسجيل الإجراء في سجل التدقيق"; refresh state after action
- [x] T022 [US3] Write `backend/tests/test_admin_lifecycle.py`: suspend → firm API blocked + audit old→new; extend-trial on cancelled firm → 422; change-plan updates subscription with audit row; missing `confirm` → 422 and no state change

**Checkpoint**: P1 scope complete — console can actually run the platform.

---

## Phase 6: User Story 4 — Billing & Subscription Oversight (P2)

**Goal**: Subscriptions view, append-only events inbox, attention queue, manual payment activation, resolve-with-note.

**Independent test**: quickstart §4 — unprocessed event in queue; resolve requires note, event row byte-identical; manual payment activates firm via shared path.

- [x] T023 [US4] Extract `activate_subscription(firm_id, plan, period_end)` from the Paymob webhook handler into `backend/app/billing/activation.py` and refactor the webhook (`backend/app/api/billing.py` or `app/billing/paymob.py` — locate actual handler) to call it; behavior byte-identical (run existing billing tests)
- [x] T024 [US4] Implement `GET /admin/subscriptions` (filters status/firm) and `GET /admin/billing-events` (`?unprocessed=true`, joined `billing_event_resolutions` as `resolved`, payload included) in `backend/app/api/admin.py`
- [x] T025 [US4] Implement `POST /admin/billing-events/{id}/resolve` (mandatory note → INSERT `billing_event_resolutions`, 409 if already resolved — `billing_events` row NEVER updated) and `POST /admin/firms/{id}/manual-payment` (INSERT `manual_payments` + call `activate_subscription()`; confirm required) in `backend/app/api/admin.py`
- [x] T026 [P] [US4] Build `frontend/app/admin/billing/page.tsx`: subscriptions table, events inbox with unprocessed/problem queue on top, payload viewer modal, resolve dialog (note required), manual payment form (amount EGP, date, reference, note, confirm)
- [x] T027 [US4] Write `backend/tests/test_admin_billing.py`: resolve without note → 422; resolve leaves `billing_events` row unchanged (before/after compare); manual payment flips subscription + firm to active and writes `manual_payments` + audit rows; webhook regression still green after T023 refactor

**Checkpoint**: Revenue exceptions handled inside the console; inbox provably append-only.

---

## Phase 7: User Story 5 — Platform Audit Log Viewer (P2)

**Goal**: Filterable platform-wide audit view; operator actions distinguishable; secrets never shown; strictly read-only.

**Independent test**: quickstart §5 — US3 actions findable by firm and by platform-actor; secret entries action-only; no mutation affordance.

- [x] T028 [US5] Implement `GET /admin/audit` in `backend/app/api/admin.py`: filters firm_id / actor / entity / action / date range / `platform_only` (context = `platform_admin`), paginated, ordered desc; rows include who/role/context/entity/record/action/old→new; each query logged via `audit_admin_read()` (entity `audit_log`, firm_id when filtered)
- [x] T029 [US5] Build `frontend/app/admin/audit/page.tsx`: filter bar, results table, row-expand showing field-level old→new diff; rows whose entity/field is a secret render the "🔑 action-only" badge (the trigger layer already stores no values — display only what arrives); zero edit/delete affordances

**Checkpoint**: Operator accountability is self-service — including watching the watcher.

---

## Phase 8: User Story 6 — Operational Health (P3)

**Goal**: Worker heartbeats + per-firm WAHA session status + recent signups, read-only.

**Independent test**: quickstart §6 — stopped worker flagged stale within 5 min; WAHA states correct.

- [x] T030 [P] [US6] Add heartbeat upserts: `backend/workers/pipeline_worker.py` and `backend/workers/scheduler_worker.py` upsert `worker_heartbeats (worker_name, last_beat=now(), details)` once per tick/pass over the service connection
- [x] T031 [US6] Implement `GET /admin/health` in `backend/app/api/admin.py`: heartbeats with `stale` = older than 5 min; WAHA `GET /api/sessions` with platform credentials mapped firm-slug → connected/disconnected/not provisioned, 30 s in-process cache, WAHA unreachable → `waha_sessions: null` + warning field (not a 500); recent signups = last 10 firms by `created_at`
- [x] T032 [US6] Build `frontend/app/admin/health/page.tsx`: worker cards with stale flag, WAHA session list, signups feed, manual refresh button — no action buttons (FR-352)

**Checkpoint**: All six stories shipped.

---

## Phase 9: Polish & Release Gate

- [x] T033 Write `backend/tests/test_admin_isolation.py` implementing the six contract checks from [contracts/rest-api.md](contracts/rest-api.md) §Isolation-suite additions: every firm role 403 on every `/admin/*` route (enumerate routes from the router, not a hand list), aal1 rejected, deactivated operator rejected, idle session rejected, firm-detail schema asserted work-product-free, no-token fail-closed — **release gate, must be green (FR-313)**
- [x] T034 [P] Document operator provisioning + revocation runbook in `docs/SAAS_RUNBOOK.md` (new §: create GoTrue user → insert `platform_operators` row → TOTP enrollment → revoke-all procedure; never a public signup)
- [ ] T035 Run the full [quickstart.md](quickstart.md) smoke pass on staging (192.168.5.61) end-to-end and record results in the quickstart file ("Executed: date / result" footer)

---

## Dependencies

```text
Phase 1 (T001–T003) → Phase 2 (T004–T008) → US1 (T009–T014) → US2 (T015–T018) → US3 (T019–T022)
                                                                        US2 done ──→ US4 (T023–T027) → US5 (T028–T029) → US6 (T030–T032)
All stories → Phase 9 (T033–T035)
```

- US1 blocks everything (no authorized requests without it).
- US2 blocks US3 (lifecycle buttons live on the detail page) and US4 (firm context).
- US4's T023 (activation extraction) is independent of US2/US3 and may start any time after Phase 2.
- US5 and US6 are independent of each other; both need US1 only — they can run in parallel with US3/US4 if staffed.

## Parallel execution examples

- **Phase 2**: T008 (models) alongside T006/T007 (operator core) — different files.
- **US1**: T012 (login page) in parallel with T009–T011 (backend) against the contract.
- **US2**: T017 (dashboard UI) in parallel with T015/T016 (endpoints).
- **US4**: T026 (billing UI) in parallel with T024/T025; T023 may start during US2/US3.
- **US6**: T030 (worker heartbeats) parallel with T031 (endpoint).

## Implementation strategy

**MVP = Phase 1 + 2 + US1** (T001–T014): a hardened, audited operator door — proves the
entire constitutional posture (fail-closed, MFA, lockout, audit) before any cross-firm
data is exposed. **First useful release = + US2 + US3** (through T022): the console can
actually run the platform. US4–US6 ship incrementally after. T033 (isolation suite) gates
the production release regardless of how many stories are included.

## Task count summary

| Phase | Tasks | Story |
|---|---|---|
| Setup | T001–T003 (3) | — |
| Foundational | T004–T008 (5) | — |
| US1 login | T009–T014 (6) | P1 |
| US2 dashboard | T015–T018 (4) | P1 |
| US3 lifecycle | T019–T022 (4) | P1 |
| US4 billing | T023–T027 (5) | P2 |
| US5 audit viewer | T028–T029 (2) | P2 |
| US6 health | T030–T032 (3) | P3 |
| Polish/gate | T033–T035 (3) | — |
| **Total** | **35** | |
