# Implementation Plan: SaaS Platform Admin Console

**Feature Directory**: `specs/003-platform-admin-console`
**Created**: 2026-06-12
**Status**: Draft
**Spec**: [spec.md](spec.md)
**Constitution**: [.specify/memory/constitution.md](../../.specify/memory/constitution.md) (v2.0.0)
**Builds on**: [specs/002-legal-platform-expansion/plan.md](../002-legal-platform-expansion/plan.md)

## Summary

Adds the platform operator surface to the multi-tenant SaaS: a dedicated `/admin` area
(frontend route group + `/admin/*` API prefix) for the SaaS operator, with hardened login
(backend-proxied GoTrue password grant + TOTP MFA + lockout + idle timeout), an all-firms
dashboard, firm lifecycle actions (suspend / reactivate / cancel / extend trial / change
plan), billing oversight (subscriptions, billing-events inbox, manual payments,
resolve-with-note), a platform audit log viewer, and an operational health panel (worker
heartbeats + per-firm WAHA session status).

The operator is the **single sanctioned cross-firm role**. The design keeps firm-side RLS
untouched: operator endpoints run on the existing service connection (BYPASSRLS) behind a
fail-closed `require_operator` dependency, expose **metadata only** (counts and platform
tables — never firm work product), and write an explicit audit entry for every cross-firm
detail read and every write **[C-I] [C-III]**.

## Technical Context

| Area | Choice |
|---|---|
| **All spec 001/002 choices** | Unchanged |
| **Operator identity** | GoTrue user in the SAME Supabase project **[C-XII]** + `platform_operators` allowlist table (source of truth; revocable). No public signup; provisioning is a documented owner runbook **[see R1]** |
| **MFA** | Supabase Auth TOTP; operator endpoints require `aal2` JWT assurance level **[see R2]** |
| **Login flow** | Backend-proxied: `POST /admin/login` calls GoTrue server-side → app-level failed-attempt tracking, lockout, and full attempt audit (frontend never talks to GoTrue directly for operators) **[see R3]** |
| **Cross-firm DB path** | Service connection (BYPASSRLS) with audit GUCs set (`app.user_id`, `app.user_role='platform_operator'`, `app.context='platform_admin'`); writes audit via existing triggers, cross-firm **reads** audit via explicit API-layer inserts **[see R4]** |
| **Sessions / idle timeout** | `operator_sessions` table keyed by JWT `session_id`; middleware enforces 30-min idle, owner can revoke one/all **[see R5]** |
| **Usage counts** | `admin_firm_usage` SQL view: per-firm count(*) aggregates only — no content columns selectable **[see R6]** |
| **Worker heartbeats** | `worker_heartbeats` upsert from pipeline/scheduler each pass; staleness threshold 5 min **[see R7]** |
| **WAHA status** | Backend queries WAHA `GET /api/sessions` with platform credentials; session name = firm slug; 30 s cache **[see R7]** |
| **Manual payments** | `manual_payments` table; activation reuses the same subscription-activation function as the Paymob webhook (one code path) **[see R8]** |
| **Event resolutions** | `billing_event_resolutions` table referencing `billing_events(id)` — the inbox row is never mutated **[C-III]** **[see R8]** |
| **Frontend** | Next.js route group `frontend/app/admin/**` with its own layout (no firm AppNav); same RTL Arabic UI |
| **Migration** | `supabase/migrations/0030_platform_admin.sql` (next free number) |

**No unresolved NEEDS CLARIFICATION** — all knobs resolved in [research.md](research.md).

## Constitution Check

*Gate evaluated before Phase 0 and re-checked after Phase 1 design.*

| # | Principle | How this feature satisfies it | Status |
|---|---|---|---|
| I | Fail-closed RLS tenant isolation | Firm-side RLS is untouched. Operator endpoints are the declared single cross-firm surface: gated by `require_operator` (JWT + aal2 + allowlist + live session), fail-closed (no operator identity ⇒ 401/403, zero data), metadata-only (`admin_firm_usage` exposes counts, never content). Isolation suite extended: every firm role rejected from every `/admin/*` endpoint; no work-product columns reachable | ✅ with declared exception (spec header; FR-310–313) |
| II | Mandatory human review gate | No AI outputs in this feature; the console cannot view, approve, or export any firm's AI outputs | ✅ |
| III | Full audit logging | Operator writes hit existing audit triggers with operator GUCs; cross-firm detail reads get explicit audit rows; login attempts (success/fail/lockout) logged; billing-events inbox stays append-only via separate resolutions table; secrets never displayed (viewer renders action-only rows) | ✅ |
| IV | Deterministic code decides | No LLM anywhere in this feature. Suspension/trial logic is plain code; scheduler's existing trial-expiry pass unchanged | ✅ |
| V | Source grounding | N/A — no AI claims produced | ✅ |
| VI | Visual AI marking | N/A — no AI output rendered | ✅ |
| VII | OCR confidence gate | N/A | ✅ |
| VIII | Assistive tool posture | Console is operator-facing ops tooling; no legal output | ✅ |
| IX | Egyptian civil-law jurisdiction | N/A | ✅ |
| X | Forfeiture deadlines | N/A — untouched | ✅ |
| XI | Self-hosting security baseline | Operator surface raises the bar: MFA mandatory, backend-proxied login with lockout, short idle sessions, revocation, no public signup, provisioning runbook requires fresh secrets | ✅ |
| XII | Stack constraint | Operator accounts are GoTrue users in the same Supabase project; all new tables in the same Postgres; no second auth system | ✅ |

**Result: PASS.** One declared, justified exception to the spirit of C-I (cross-firm
visibility), resolved exactly as the constitution's amendment for SaaS anticipates: the
operator is the platform-running role, restricted to metadata, fail-closed, fully audited,
and adversarially tested. Logged in Complexity Tracking below.

## Project Structure

### Documentation (this feature)

```text
specs/003-platform-admin-console/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0 — resolved decisions R1–R8
├── data-model.md        # Phase 1 — new entities, grants, audit coverage
├── quickstart.md        # Phase 1 — end-to-end smoke-test path
├── contracts/
│   ├── rest-api.md      # /admin/* API surface
│   └── ui-screens.md    # screen → access → actions contract
└── checklists/
    └── requirements.md
```

### Source code additions

```text
frontend/app/admin/
├── layout.tsx           # operator shell: own nav, operator session guard
├── login/page.tsx       # credential + TOTP challenge (talks only to backend)
├── page.tsx             # all-firms dashboard (status, plan, trial, usage, attention flags)
├── firms/[id]/page.tsx  # firm detail + lifecycle actions (confirm dialogs)
├── billing/page.tsx     # subscriptions + events inbox + attention queue
├── audit/page.tsx       # platform audit log viewer (filters, old→new diffs)
└── health/page.tsx      # worker heartbeats + WAHA session status

frontend/lib/adminApi.ts # fetch wrapper for /admin/* (operator token, 401→/admin/login)

backend/app/api/admin.py         # all /admin/* routes
backend/app/core/operator.py     # require_operator dependency: JWT→aal2→allowlist→session
backend/app/billing/activation.py# extracted shared subscription-activation (webhook + manual)
backend/workers/…                # pipeline/scheduler: heartbeat upsert per pass

supabase/migrations/
└── 0030_platform_admin.sql      # platform_operators, operator_sessions,
                                 #   operator_login_attempts, manual_payments,
                                 #   billing_event_resolutions, worker_heartbeats,
                                 #   admin_firm_usage view, audit triggers, grants
```

## Architecture

### Operator authentication chain (fail-closed at every link)

```text
Browser /admin/login
  → POST /admin/login {email, password}            (backend only — never direct GoTrue)
      backend: lockout check (operator_login_attempts)
      backend → GoTrue password grant (server-side)
      ok + MFA enrolled → 200 {mfa_required, factor_id}   | every attempt audit-logged
  → POST /admin/mfa/verify {factor_id, code}
      backend → GoTrue MFA challenge+verify → aal2 token
      backend: platform_operators allowlist row must exist & be active
      backend: INSERT operator_sessions (session_id, last_seen)
      → 200 {access_token}
Every /admin/* request → require_operator:
      verify JWT (ES256 JWKS, same as firm auth) → require aal=aal2
      → allowlist active? → session row fresh (<30 min idle)? → update last_seen
      any link fails ⇒ 401/403, zero rows               [C-I posture]
```

### Cross-firm access & audit

```text
/admin/* handler → service connection (BYPASSRLS)
   SET app.user_id = <operator auth id>, app.user_role = 'platform_operator',
       app.context = 'platform_admin'
   writes  → existing audit triggers record who/what/old→new       [C-III]
   firm-detail reads & audit-viewer queries → explicit audit INSERT
       (action='admin_read', entity, record_id, firm_id)            [C-III]
   data exposed: firms, subscriptions, billing_events(+payload),
       audit_log, admin_firm_usage (counts), worker_heartbeats, WAHA status
   never selectable: case/document/contact/ai_output content columns
```

### Manual payment activation (single code path with webhook)

```text
Paymob webhook ──┐
                 ├─→ billing/activation.py::activate_subscription(firm, plan, period)
POST /admin/firms/{id}/manual-payment ─┘        → subscriptions.status='active'
                                                → firms.status='active'
                                                → audit rows (trigger)
manual path additionally INSERTs manual_payments (amount, date, reference, note, operator)
```

## Phase 0 — Research

See [research.md](research.md). Resolves: operator identity via GoTrue + allowlist (R1),
TOTP/aal2 MFA (R2), backend-proxied login with lockout (R3), service-connection cross-firm
path with explicit read audit (R4), idle sessions + revocation (R5), metadata-only usage
view (R6), heartbeats + WAHA polling (R7), manual payments + resolutions sharing the
webhook activation path (R8).

## Phase 1 — Design & Contracts

- [data-model.md](data-model.md) — 6 new tables + 1 view, grants (service-context only),
  audit coverage, operator session state machine.
- [contracts/rest-api.md](contracts/rest-api.md) — `/admin/*` API surface.
- [contracts/ui-screens.md](contracts/ui-screens.md) — screen → access → actions contract.
- [quickstart.md](quickstart.md) — smoke-test path (provision operator → login+MFA →
  suspend/reactivate firm → manual payment → audit verify → isolation checks).
- Agent context: `CLAUDE.md` active-feature block updated to point at this plan.

## Complexity Tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| Single cross-firm role (operator) atop C-I's no-cross-firm rule | A multi-tenant SaaS cannot be operated without a platform-level view of firms, billing, and health; today this is done over raw SQL with no audit trail — strictly worse | "Keep using SQL" has no MFA, no lockout, no read audit, no metadata boundary; per-firm admin accounts can't see billing events or platform health at all |

## Phasing (maps spec user stories → build order)

| Build phase | Spec stories | Gate before next |
|---|---|---|
| Phase A — Operator auth foundation | US1 (FR-301–306, 312) | Migration applied; login+MFA+lockout+idle+revocation all pass; every firm role rejected from a probe `/admin/me`; attempts audit-logged |
| Phase B — Firms dashboard + lifecycle | US2, US3 (FR-310–311, 320–324) | Suspend/reactivate/extend/change-plan working end-to-end with audit old→new; usage = counts only; detail reads audit-logged |
| Phase C — Billing oversight | US4 (FR-330–334) | Manual payment activates via shared path; inbox append-only proven; resolution requires note |
| Phase D — Audit viewer | US5 (FR-340–342) | Filters work; operator actions distinguishable; secret rows render action-only |
| Phase E — Operational health | US6 (FR-350–352) | Stale-worker flag within threshold; WAHA states correct; read-only verified |
| Phase F — Isolation suite extension | FR-313 | Extended adversarial suite green — release gate |
