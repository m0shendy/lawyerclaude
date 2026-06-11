# CLAUDE.md

Guidance for AI agents working in this repository.

## Project

AI-assisted, **multi-tenant SaaS** office-management system for Egyptian (civil-law)
law firms (constitution v2). Arabic RTL dashboard over a Python AI engine; one Supabase Cloud
project for all firms with **fail-closed RLS tenant isolation** (every tenant table carries
`firm_id`; no firm context ⇒ zero rows). Firms sign up at `/signup` (14-day trial) and pay via
Paymob. Deployment: `docs/SAAS_RUNBOOK.md`. The v1 per-firm stack lives in `infra/legacy/`
for a future Enterprise dedicated-instance tier.

## Authoritative documents (read before changing anything)

- **Constitution** — [.specify/memory/constitution.md](.specify/memory/constitution.md) (v1.0.0).
  12 **inviolable** principles. If any instruction conflicts with them, STOP and surface it.
- **Build plan** — [BUILD_PLAN_DETAILED.md](BUILD_PLAN_DETAILED.md).

<!-- SPECKIT START -->
### Active feature: AI-Assisted Lawyer Office Management System
- Plan: [specs/001-lawyer-office-management/plan.md](specs/001-lawyer-office-management/plan.md)
- Spec: [specs/001-lawyer-office-management/spec.md](specs/001-lawyer-office-management/spec.md)
- Research: [specs/001-lawyer-office-management/research.md](specs/001-lawyer-office-management/research.md)
- Data model: [specs/001-lawyer-office-management/data-model.md](specs/001-lawyer-office-management/data-model.md)
- Contracts: [specs/001-lawyer-office-management/contracts/](specs/001-lawyer-office-management/contracts/)
- Quickstart: [specs/001-lawyer-office-management/quickstart.md](specs/001-lawyer-office-management/quickstart.md)
<!-- SPECKIT END -->

## Stack (locked)

- **Frontend**: Next.js 14 + TypeScript, RTL-first Arabic.
- **Backend / AI engine**: Python 3.12 + FastAPI (+ background worker entrypoints).
- **Data/Auth/Storage/RAG**: Supabase Cloud (Postgres + pgvector + GoTrue + Storage), one
  shared project, RLS tenant isolation keyed by `app.firm_id`. **No MS SQL Server. Auth and
  data stay in the same Supabase project.**
- **Infra**: API + workers on a container host; frontend on Vercel; WAHA Plus alongside
  (per-firm session = firm slug). Per-firm Docker/Traefik stack retired to `infra/legacy/`.
- **WhatsApp**: WAHA Plus (Sumopod), per-firm session = tenant id.
- **OCR**: Google Document AI (live intake); Foxit Pro + direct extraction (shared corpus, once).
- **LLM**: client-provided key (default rec. Gemini 3.1 Pro); embeddings separate/cheaper.

## Architecture invariants (do not violate)

- AI is **three separate components**: (A) deterministic Retriever, (B) generation-only LLM,
  (C) deterministic Scheduler. Reminders/reports never go through an agent.
- Every AI output is born `draft_unreviewed`, AI-marked, source-grounded; export/send blocked
  until an **assigned lawyer or partner** approves. No bypass path.
- Every create/update/delete is audit-logged append-only (DB triggers); secrets logged as
  action-only, never as values.
- Appeal-deadline suggestions are confirm-required, behind a feature flag, off until expert
  sign-off.
- Shared Egyptian-law corpus is read-only, public law only — no firm/client data ever enters it.

## Repo layout

`frontend/` · `backend/` (`app/{api,retriever,llm,scheduler,pipeline,audit,core,models}`,
`workers/`) · `supabase/` (migrations) · `infra/` (compose, traefik, provision, backup,
security) · `shared-corpus/` (one-time central prep).
