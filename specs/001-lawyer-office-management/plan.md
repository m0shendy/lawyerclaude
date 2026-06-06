# Implementation Plan: AI-Assisted Lawyer Office Management System

**Feature Directory**: `specs/001-lawyer-office-management`
**Created**: 2026-06-05
**Status**: Draft
**Spec**: [spec.md](spec.md)
**Constitution**: [.specify/memory/constitution.md](../../.specify/memory/constitution.md) (v1.0.0)

## Summary

A per-firm **physically isolated** instance hosting an Arabic, RTL-first dashboard (Next.js 14 +
TypeScript) over a Python/FastAPI AI engine, backed by self-hosted Supabase (Postgres + GoTrue +
Storage + pgvector) — one full Docker stack per firm. AI is built as **three separate
components**: (A) a deterministic Retriever that embeds queries and searches pgvector across the
firm's private corpus + a read-only shared Egyptian-law corpus; (B) the LLM, generation-only, on
the client's API key; (C) a deterministic Orchestrator/Scheduler that fires on time, queries
confirmed data, sends via WAHA WhatsApp, and writes `notifications_log` — the LLM only phrases
report prose. A background worker runs the document pipeline (upload → Storage → Document AI OCR
→ confidence gate → mandatory Arabic normalization → chunk → embed → pgvector). Every AI output
is born `draft_unreviewed`; every mutation is audit-logged append-only. Demo (home server, dummy
data, Cloudflare Tunnel) and production (VPS) run the **same** Docker stack so promotion is a
lift-and-shift deployment, with a repeatable per-firm provisioning script and a self-hosting
security baseline (fresh secrets, SSL, protected Studio, firewall, tested per-firm backups).

## Technical Context

| Area | Choice |
|---|---|
| **Frontend** | Next.js 14 (App Router) + TypeScript, RTL-first Arabic, Supabase JS client (GoTrue auth) |
| **Backend / AI engine** | Python 3.12 + FastAPI; background worker (same image, worker entrypoint) |
| **Data + Auth + Storage + RAG** | Self-hosted Supabase: Postgres 15 + pgvector, GoTrue, Storage. One stack per firm. **No MS SQL Server. No split cloud auth.** **[C-XII]** |
| **Containerization** | Docker + docker-compose (official Supabase self-host compose) |
| **Orchestration / proxy** | Portainer (manage stacks); Traefik (subdomain → firm container) + wildcard DNS + wildcard Let's Encrypt TLS |
| **WhatsApp** | WAHA Plus on Sumopod; per-firm WAHA session = tenant identifier; config in `firm_settings` |
| **OCR (live intake)** | Google Document AI (Enterprise Document OCR) in async background worker |
| **OCR (shared corpus, one-time)** | Foxit Pro (image files) + direct text extraction (text PDFs); embed shared corpus ONCE centrally |
| **LLM (generation)** | Client-provided API key (default rec. Gemini 3.1 Pro); generation only, no tool-acting in scheduler |
| **Embedding model** | Separate, cheaper model; multilingual (Arabic-capable). Decision in research.md |
| **Scheduling** | Deterministic scheduler in backend (APScheduler/cron-style worker); never an agent **[C-IV]** |
| **Scale assumptions** | Per firm: tens of users, low-thousands of cases, tens-of-thousands of documents/chunks |
| **Performance** | Standard web expectations; OCR + embedding are async/background, not request-blocking |

**Resolved research knobs** (see [research.md](research.md)): embedding model & dimensionality,
pgvector index type (HNSW), chunk size/overlap, Document AI confidence threshold, reminder lead
points, Arabic normalization ruleset, audit-capture mechanism (DB triggers vs app layer).

**No unresolved NEEDS CLARIFICATION** — the stack is fully specified by the user; remaining knobs
are resolved with defaults in research.md and may be tuned at the Phase 1 OCR checkpoint.

## Constitution Check

*Gate evaluated before Phase 0 and re-checked after Phase 1 design. All principles PASS.*

| # | Principle | How the design satisfies it | Status |
|---|---|---|---|
| I | Per-firm physical isolation | One Docker stack + Supabase + DB + auth + storage per firm; Traefik routes subdomain→firm container; RLS used only for in-instance role access, never cross-firm | ✅ |
| II | Mandatory human review gate | `ai_outputs.review_state` defaults `draft_unreviewed`; export/print/send endpoints reject non-`approved`; DB constraint + API guard; no bypass path | ✅ |
| III | Full audit logging | DB-trigger-based append-only `audit_log` on every table (who/role/when/entity/action/old→new); REVOKE update/delete on audit_log; secrets logged as action-only | ✅ |
| IV | Deterministic code decides; AI only phrases | Scheduler (component C) is plain code querying confirmed rows; LLM only phrases report prose; reminders/reports never routed through an agent | ✅ |
| V | Source grounding | `ai_outputs.source_links` → `document_chunks` (page/location); generation prompt requires per-claim citations; UI renders links | ✅ |
| VI | Visual AI marking | Unapproved outputs render "AI-generated — requires review" banner; enforced in shared UI component | ✅ |
| VII | OCR confidence gate | `documents.ocr_confidence` + `low_confidence` status; derived outputs set `low_confidence_flag`; UI shows heightened warning / double-review path | ✅ |
| VIII | Assistive tool, not legal advice | Persistent UI disclaimer, assistant system prompt, ToS copy; risk/reference outputs carry posture text | ✅ |
| IX | Egyptian civil law; persuasive only | Reference/precedent + risk outputs labeled istishhad; prompts forbid binding-precedent/outcome-prediction framing | ✅ |
| X | Forfeiture deadlines confirm-required | Appeal deadlines created as suggestions (`confirmed=false`), behind feature flag, inert until "Verified & Confirmed"; flag off until expert sign-off | ✅ |
| XI | Self-hosting security baseline | Fresh secrets per provision, Traefik wildcard SSL, Studio behind auth/network-restricted, firewall, tested per-firm backups (infra/) | ✅ |
| XII | Stack constraint | Postgres + pgvector via self-hosted Supabase; no MS SQL; auth (GoTrue) co-located with data | ✅ |

**Result: PASS — no deviations, no entries in Complexity Tracking.**

## Project Structure

### Documentation (this feature)

```text
specs/001-lawyer-office-management/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0 — resolved decisions
├── data-model.md        # Phase 1 — entities, relationships, RLS, audit, state machines
├── quickstart.md        # Phase 1 — provision a firm instance & run the pipeline end-to-end
├── contracts/
│   ├── README.md
│   ├── rest-api.md      # FastAPI endpoints (auth, RBAC, review gate, pipeline, deadlines…)
│   ├── whatsapp.md      # WAHA inbound/outbound contract (assistant + reminders + reports)
│   └── ui-screens.md    # screen → role → actions contract
└── checklists/
    └── requirements.md
```

### Source code (repository root)

```text
frontend/                       # Next.js 14 + TS, RTL Arabic dashboard
├── app/                        # App Router: login, dashboard, cases, documents,
│   │                           #   ai-review, deadlines, tasks, assistant, reports,
│   │                           #   settings, users, audit
├── components/                 # incl. <AiMarkedOutput/>, <ReviewGate/>, <Disclaimer/>
├── lib/                        # supabase client, api client, rbac helpers, i18n/RTL
└── tests/

backend/                        # Python + FastAPI AI engine
├── app/
│   ├── api/                    # routers (cases, documents, ai_outputs, deadlines,
│   │                           #   tasks, reports, settings, users, audit, assistant)
│   ├── retriever/              # Component A — embed query + pgvector search (private+shared)
│   ├── llm/                    # Component B — generation only (client key)
│   ├── scheduler/              # Component C — deterministic reminders/reports + WAHA
│   ├── pipeline/               # OCR worker: preprocess→DocAI→confidence→normalize→chunk→embed
│   ├── audit/                  # audit helpers / verification
│   ├── core/                   # config, security, db, feature flags
│   └── models/                 # pydantic + db schema models
├── workers/                    # background worker entrypoints (pipeline, scheduler)
└── tests/

supabase/                       # per-firm self-hosted stack
├── migrations/                 # SQL: schema, pgvector, RLS (in-instance roles),
│   │                           #   audit triggers, review-gate constraints
└── seed/                       # dummy data (DEMO ONLY — never real client docs)

infra/
├── docker-compose.yml          # app + Supabase self-host (same home & VPS)
├── traefik/                    # reverse proxy, wildcard DNS, Let's Encrypt TLS
├── provision/                  # repeatable per-firm instance provisioning script
├── backup/                     # per-firm automated backup + restore-test
└── security/                   # secrets generation, firewall, Studio protection baseline

shared-corpus/                  # ONE-TIME central prep (Foxit/extract → normalize → embed once)
```

**Structure decision**: Monorepo with three deployable concerns — `frontend` (dashboard),
`backend` (FastAPI API + background workers, one image two entrypoints), and `supabase` (the
per-firm data stack) — wired together by `infra/docker-compose.yml`. The same compose runs on
the home demo server and the production VPS; `infra/provision` scripts the per-firm instance.

## Architecture: AI as three components

```text
            ┌─────────────────────────── Per-firm instance (Docker stack) ───────────────────────────┐
  Browser ──┤ Traefik → Next.js dashboard → FastAPI                                                   │
  WhatsApp ─┤                                  │                                                       │
            │   (A) Retriever  ── embeds query, pgvector search over [private + shared] → chunks       │
            │   (B) LLM        ── generation only, client key, reasons over chunks → draft + citations │
            │   (C) Scheduler  ── deterministic: time-fire → query CONFIRMED data → WAHA → log         │
            │                                                                                           │
            │   Postgres+pgvector · GoTrue · Storage   |   shared corpus (read-only, public law)       │
            └───────────────────────────────────────────────────────────────────────────────────────┘
```

- **A (Retriever)** is application code, not the LLM — it never "decides," it retrieves. **[C-V]**
- **B (LLM)** generates only; output enters `draft_unreviewed` with per-claim source links. **[C-II][C-V]**
- **C (Scheduler)** is deterministic; the LLM may phrase report prose but never selects/omits
  items or decides whether a reminder fires. A missed deadline traces to data, not judgment. **[C-IV]**

## Document pipeline (background worker)

```text
upload → Storage + documents row = pending
  → worker: image pre-process
  → Google Document AI (Enterprise Document OCR)
  → confidence gate  ── below threshold ⇒ status=low_confidence (+ heightened warning downstream)
  → Arabic normalization (MANDATORY: unify alef forms, ta-marbuta, strip diacritics, clean artifacts)
  → chunk (size/overlap per research.md)
  → embed (embedding model) → document_chunks.embedding (pgvector)
  → status = ready   (or failed on hard error, surfaced to user)
```

**Phase 1 checkpoint (from build plan):** before building further, STOP and validate Document AI
confidence on a real sample of the firm's actual scans — that number gates every downstream
output. **[C-VII]**

## Deployment & security baseline

- **Same stack, two environments.** Demo = home server, dummy data only, exposed via Cloudflare
  Tunnel (no open router ports). Production = VPS. Home→VPS is a **deployment (lift-and-shift)**,
  not a live-data migration, because home holds only dummy data.
- **Per-firm provisioning** (`infra/provision`): stand up a new firm stack with **fresh** secrets
  (new JWT/GoTrue secrets — never defaults), its WAHA session, subdomain + Traefik route, and
  baked-in/linked shared corpus. Becomes worthwhile to fully automate after ~3–4 firms; scripted
  from day one regardless. **[C-XI]**
- **Security baseline** (`infra/security`, `infra/backup`): fresh secrets, SSL everywhere
  (wildcard Let's Encrypt via Traefik), Supabase Studio not publicly exposed (network-restricted
  + auth), host firewall, and **per-firm automated backups tested for restore** before any real
  firm is onboarded. **[C-XI]**

See [quickstart.md](quickstart.md) for the end-to-end provision + smoke-test path.

## Phase 0 — Research

See [research.md](research.md). Resolves: embedding model & dimension, pgvector index (HNSW vs
IVFFlat), chunk size/overlap, Document AI confidence threshold, Arabic normalization ruleset,
audit capture (DB triggers), review-gate enforcement (DB + API), scheduler technology, feature
flag mechanism, and shared-corpus delivery (central read-only vs baked-in).

## Phase 1 — Design & Contracts

- [data-model.md](data-model.md) — 13 entities, relationships, RLS (in-instance roles), append-only
  audit, review-gate + confirm-required state machines.
- [contracts/](contracts/) — REST API, WhatsApp (WAHA) contract, UI screen/role/action contract.
- [quickstart.md](quickstart.md) — provision a firm and run a document end-to-end through the gate.
- Agent context: `CLAUDE.md` updated with a pointer to this plan (between SPECKIT markers).

## Complexity Tracking

*No constitutional deviations. No complexity exceptions required.*

## Phasing (maps spec user stories → build order)

| Build phase | Spec stories | Gate before next |
|---|---|---|
| Phase 0 — Foundation & isolation | US1 | Isolated instance: auth, roles, **audit log**, cases, document upload+status |
| Phase 1 — Pipeline + quality gate | US1/US2 prep | **Document AI confidence validated on real scans** (STOP point) |
| Phase 2 — Summarization/extraction + REVIEW GATE | US2 | Reviewed, audited, grounded, AI-marked outputs |
| Phase 3 — Deadlines/reminders + manager reports (deterministic) | US3, US4 | Escalating reminders + reports logged |
| Phase 3b — Appeal-deadline suggestions (flagged) | US5 | Behind flag; expert sign-off before user enable |
| Phase 4 — Conversational assistant (agentic OK) | US6 | Identity-scoped, grounded, gated |
| Phase 5 — Contract analysis | US7 | Gated, grounded |
| Phase 6 — Reference/precedent (persuasive) | US8 | istishhad framing |
| Phase 7 — Risk signals (not prediction) | US9 | Assistive posture, gated |
