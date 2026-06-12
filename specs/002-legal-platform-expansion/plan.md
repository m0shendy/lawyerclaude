# Implementation Plan: Legal Platform Expansion

**Feature Directory**: `specs/002-legal-platform-expansion`
**Created**: 2026-06-08
**Status**: Draft
**Spec**: [spec.md](spec.md)
**Constitution**: [.specify/memory/constitution.md](../../.specify/memory/constitution.md) (v1.0.0)
**Builds on**: [specs/001-lawyer-office-management/plan.md](../001-lawyer-office-management/plan.md)

## Summary

This spec extends the foundation from spec 001 by adding 42 new functional requirements across six
capability groups — all within the **same per-firm Docker stack**, leveraging the existing
pipeline, audit, and review-gate infrastructure. The additions are:

1. **Six new AI features**: AI document drafting (contracts / court submissions / engagement
   letters), AI contract review with clause taxonomy, AI letter pack generation, AI case timeline
   generation, AI knowledge search UI, and multi-provider LLM configuration.
2. **Client management**: auto-numbered client records, typed contacts, built-in conflict check.
3. **Document Management System (DMS)**: folder hierarchies, full version control, pessimistic
   check-in/out, access levels, confidentiality flags, template library, selective client sharing.
4. **Billing & invoicing**: auto-numbered invoices, line items, Egyptian payment methods, invoice
   lifecycle, service catalog.
5. **Hearing management + Appointment scheduling + Unified calendar**: Egyptian civil court hearing
   types, appointment conflict detection, month/week calendar view aggregating both.
6. **Client portal**: per-instance isolated portal for the new `client` role, scoped strictly to
   own matters/documents/invoices/consultations. AI insights shown only post-approval.
7. **Analytics & reporting**: Admin-only dashboard KPIs (from materialized views), financial and
   operational reports, activity feed from audit log.
8. **Task enhancements**: priority levels and advanced filtering (extends spec 001 FR-042).

All AI outputs added here are born `draft_unreviewed`, source-grounded, and AI-marked —
identical posture to spec 001. All new mutations are append-only audit-logged via DB triggers.

## Technical Context

| Area | Choice |
|---|---|
| **All spec 001 choices** | Unchanged — see [spec 001 plan.md](../001-lawyer-office-management/plan.md) |
| **Multi-provider LLM** | **LiteLLM** proxy/library as the firm-level abstraction; per-firm provider + API key in `firm_settings.llm_provider_config` (extends existing `llm_api_key`) **[see R1]** |
| **Doc version storage** | Each version stored as a separate file in Supabase Storage; `document_versions` table tracks root→prev→current chain **[see R2]** |
| **Doc check-out locking** | Pessimistic row-level lock: `document_checkouts` table row; checked-out docs refused for simultaneous check-out at API layer **[see R3]** |
| **Auto-numbering** | Postgres sequences for CASE-XXXX, CL-XXXXXX; INV-YYYYMM-XXXXXX uses a per-year-month counter stored in a sequences helper table **[see R4]** |
| **Conflict check** | Postgres `tsvector` full-text index on opposing-party / client name fields; search across active matters; runs on save **[see R5]** |
| **Analytics KPIs** | Materialized views refreshed on each relevant mutation (via trigger or post-write API call); reports run on-demand against live data **[see R6]** |
| **Calendar aggregation** | Postgres view (`calendar_events`) UNIONing `hearings` + `appointments`; no separate table **[see R7]** |
| **Client portal auth** | Same Supabase GoTrue instance; `client` role in JWT claim; RLS policies restrict rows to `client_id` linkage **[see R8]** |
| **Document templates** | Mustache-style variable substitution for deterministic fields; AI fills contextual/substantive fields and still produces `draft_unreviewed` output **[see R9]** |
| **Hearing reminders** | Same deterministic scheduler component (spec 001 R8) extended with hearing reminder jobs **[see R10]** |
| **New AI output types** | Extend `ai_outputs.type` enum: add `doc_draft` · `letter_pack` · `case_timeline`; existing `analysis`/`clause_flag`/`risk_signal` unchanged |

**No unresolved NEEDS CLARIFICATION** — all knobs are resolved in [research.md](research.md).

## Constitution Check

*Gate evaluated before Phase 0 and re-checked after Phase 1 design. All principles PASS.*

| # | Principle | How this expansion satisfies it | Status |
|---|---|---|---|
| I | Per-firm physical isolation | Client portal served from firm's own instance; `client` role RLS restricts rows to own data; no cross-firm portal infrastructure | ✅ |
| II | Mandatory human review gate | All new AI outputs (doc_draft, letter_pack, case_timeline, clause findings, risk flags) born `draft_unreviewed`; portal surfaces only `approved` AI insights; no new bypass path | ✅ |
| III | Full audit logging | All 14 new/extended entities receive DB-trigger audit coverage (see data-model.md); invoice/payment/version check-in/check-out all audit-logged | ✅ |
| IV | Deterministic code decides; AI only phrases | Hearing reminders via same deterministic scheduler as deadlines; analytics KPIs from materialized views / live queries, not LLM; report prose may be AI-phrased only after data selection | ✅ |
| V | Source grounding | AI doc drafts, contract reviews, letter packs, and case timelines all require per-claim source links stored in `ai_outputs.source_links`; generation prompts enforce citations | ✅ |
| VI | Visual AI marking | New AI output types rendered by the existing `<AiMarkedOutput/>` component; no new unguarded display paths | ✅ |
| VII | OCR confidence gate | AI doc generation / contract review from `low_confidence` source documents inherits the heightened warning flag; `low_confidence_flag` propagated to new output types | ✅ |
| VIII | Assistive tool posture | Client portal AI insights carry assistive-tool disclaimer; AI-drafted legal documents carry the disclaimer; letter packs carry the posture text | ✅ |
| IX | Egyptian civil law; persuasive only | Hearing types default to Egyptian civil court taxonomy; AI-drafted documents citing authority use استشهاد framing; no outcome-predictive outputs added | ✅ |
| X | Forfeiture deadlines confirm-required | No new forfeiture deadline logic added in this spec; existing flag and confirm-required gate from spec 001 remain unchanged | ✅ |
| XI | Self-hosting security baseline | Client portal runs inside the same secured per-firm instance; no new public-facing services with separate credentials; all new secrets (none added) would follow fresh-secrets rule | ✅ |
| XII | Stack constraint | All new entities in Postgres via self-hosted Supabase; file versions in Supabase Storage; no external auth split; no MS SQL | ✅ |

**Result: PASS — no deviations. No entries in Complexity Tracking.**

## Project Structure

### Documentation (this feature)

```text
specs/002-legal-platform-expansion/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0 — resolved decisions R1–R10
├── data-model.md        # Phase 1 — new/extended entities, RLS, audit, state machines
├── quickstart.md        # Phase 1 — end-to-end smoke-test path for new features
├── contracts/
│   ├── rest-api.md      # new FastAPI endpoints (clients, DMS, billing, hearings,
│   │                    #   appointments, portal, analytics, AI features)
│   └── ui-screens.md    # new screen → role → actions contract
└── checklists/
    └── requirements.md
```

### Source code additions (repository root)

All additions live inside the existing monorepo layout. New files only — no existing
files from spec 001 are deleted.

```text
frontend/app/
├── clients/             # Client management, conflict check
├── documents/           # DMS: folders, versions, check-out, templates
├── billing/             # Invoices, payments, service catalog
├── hearings/            # Hearing management
├── appointments/        # Appointment scheduling
├── calendar/            # Unified calendar view
├── portal/              # Client portal (client role only)
├── analytics/           # Admin-only analytics & reporting
└── (existing screens from spec 001 extended where needed)

backend/app/api/
├── clients.py           # Client CRUD, conflict check
├── dms.py               # Document folders, versions, check-in/out, sharing, templates
├── billing.py           # Invoices, invoice items, payments, service catalog
├── hearings.py          # Hearing CRUD + reminders
├── appointments.py      # Appointment CRUD + conflict detection
├── calendar.py          # Aggregated calendar view endpoint
├── portal.py            # Client portal scoped endpoints
├── analytics.py         # Dashboard KPIs, financial/operational reports, activity feed
├── ai_doc.py            # AI document drafting (doc_draft, letter_pack, case_timeline)
└── (existing routers from spec 001 extended where needed)

backend/app/llm/
└── providers.py         # LiteLLM wrapper, per-firm provider dispatch

supabase/migrations/
└── 0017_expansion.sql   # New tables, extended tables, RLS for client role,
                         #   audit triggers for new tables, sequences, materialized views
```

## Architecture additions

### Multi-provider LLM dispatch

```text
  API request (doc_draft / letter_pack / contract_review / …)
    → backend/app/llm/providers.py
    → reads firm_settings.llm_provider_config { provider, model, api_key }
    → LiteLLM.completion(model=<provider>/<model>, …)
    → response → ai_outputs (draft_unreviewed, source_links)  [C-II]
```

All new AI output types follow the same pipeline as spec 001: retrieval (Component A) →
LiteLLM generation (Component B) → `draft_unreviewed` row + source links. The LLM provider
switch requires no code changes — only a firm Settings update.

### Client portal isolation

```text
  Browser (client user) → Traefik (firm subdomain) → same Next.js instance
    → GoTrue auth → JWT { role: "client", client_id: … }
    → /portal/** routes (Next.js route group, client-role gated)
    → API /portal/* endpoints → RLS: WHERE client_id = auth.uid()
    → returns only: own matters, shared non-confidential docs, own invoices,
                    own consultations, approved AI insights
```

The `client` portal route group and API prefix are separate from the main app routes,
but served from the same per-firm Docker instance — preserving physical isolation **[C-I]**.

### Document version control

```text
  Check-out: INSERT document_checkouts (doc_id, user, timestamp) → doc locked
  Edit (client-side or upload new version)
  Check-in: INSERT document_versions (doc_id, version++, new_file_path, prev_version_id)
           DELETE document_checkouts WHERE doc_id
           → audit_log entry for both check-out and check-in events
  Version navigation: traverse document_versions.prev_version_id chain back to root
```

### Hearing reminders (extension of spec 001 scheduler)

```text
  Scheduler fires daily (Africa/Cairo 08:00) — existing cron job extended:
    + Query hearings WHERE scheduled_at BETWEEN now() AND now()+7d
                     AND notified_at IS NULL
    → send WAHA notification to assigned lawyer
    → INSERT notifications_log  [C-IV]
```

## Phase 0 — Research

See [research.md](research.md). Resolves: LiteLLM for multi-provider dispatch, pessimistic
check-out locking, version storage strategy, auto-numbering for CASE/CL/INV, conflict-check
via tsvector, materialized-view KPIs, calendar aggregation as a DB view, client portal auth
via GoTrue role claim, Mustache + AI document templates, and hearing reminder scheduling.

## Phase 1 — Design & Contracts

- [data-model.md](data-model.md) — 14 new/extended entities, RLS additions for `client` role,
  new audit trigger coverage, state machines for invoices and document versions.
- [contracts/rest-api.md](contracts/rest-api.md) — new API surface (clients, DMS, billing,
  hearings, appointments, calendar, portal, analytics, AI document features).
- [contracts/ui-screens.md](contracts/ui-screens.md) — new screen → role → action contract.
- [quickstart.md](quickstart.md) — smoke-test path covering the expansion features.
- Agent context: `CLAUDE.md` SPECKIT block updated to point to this plan.

## Complexity Tracking

*No constitutional deviations. No complexity exceptions required.*

## Phasing (maps spec user stories → build order)

| Build phase | Spec stories | Gate before next |
|---|---|---|
| Phase A — Client management + extended matters | US3, matter extensions (FR-108–FR-118) | Client CRUD, conflict check, auto-numbers working; existing matter UI extended |
| Phase B — DMS: version control + check-in/out | US4 (FR-112–FR-117) | Version chain intact, check-out lock prevents double-edit, audit trail verified |
| Phase C — Billing & invoicing | US5 (FR-119–FR-123) | Invoice lifecycle complete, payment recording, audit entries |
| Phase D — Hearings + Appointments + Calendar | US6, US7, US8 (FR-124–FR-131) | Hearing reminders fire via deterministic scheduler; appointment conflict detection; calendar aggregated |
| Phase E — AI document features | US1, US2, US11, US12, US13 (FR-101–FR-107, FR-141) | All AI outputs born `draft_unreviewed`, grounded, AI-marked, gated; multi-provider LLM switching verified |
| Phase F — Client portal | US9 (FR-132–FR-135) | Cross-client isolation verified; no draft_unreviewed AI content visible to client |
| Phase G — Analytics & reporting | US10 (FR-136–FR-140) | KPIs reconcile to audit log; Admin-only gate enforced |
| Phase H — Task enhancements | FR-142 | Priority + advanced filter working on existing tasks |
