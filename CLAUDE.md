# CLAUDE.md

Guidance for AI agents working in this repository.

## Project

AI-assisted, **per-firm physically isolated** office-management system for Egyptian (civil-law)
law firms. Arabic RTL dashboard over a Python AI engine, self-hosted Supabase per firm.

## Authoritative documents (read before changing anything)

- **Constitution** — [.specify/memory/constitution.md](.specify/memory/constitution.md) (v1.0.0).
  12 **inviolable** principles. If any instruction conflicts with them, STOP and surface it.
- **Build plan** — [BUILD_PLAN_DETAILED.md](BUILD_PLAN_DETAILED.md).

<!-- SPECKIT START -->
### Active feature: Legal Platform Expansion
- Plan: [specs/002-legal-platform-expansion/plan.md](specs/002-legal-platform-expansion/plan.md)
- Spec: [specs/002-legal-platform-expansion/spec.md](specs/002-legal-platform-expansion/spec.md)
- Research: [specs/002-legal-platform-expansion/research.md](specs/002-legal-platform-expansion/research.md)
- Data model: [specs/002-legal-platform-expansion/data-model.md](specs/002-legal-platform-expansion/data-model.md)
- Contracts: [specs/002-legal-platform-expansion/contracts/](specs/002-legal-platform-expansion/contracts/)
- Quickstart: [specs/002-legal-platform-expansion/quickstart.md](specs/002-legal-platform-expansion/quickstart.md)
### Foundation feature: AI-Assisted Lawyer Office Management System
- Plan: [specs/001-lawyer-office-management/plan.md](specs/001-lawyer-office-management/plan.md)
- Spec: [specs/001-lawyer-office-management/spec.md](specs/001-lawyer-office-management/spec.md)
<!-- SPECKIT END -->

## Stack (locked)

- **Frontend**: Next.js 14 + TypeScript, RTL-first Arabic.
- **Backend / AI engine**: Python 3.12 + FastAPI (+ background worker entrypoints).
- **Data/Auth/Storage/RAG**: self-hosted Supabase (Postgres + pgvector + GoTrue + Storage), one
  stack per firm. **No MS SQL Server. No split cloud auth.**
- **Infra**: Docker + docker-compose, Portainer, Traefik (wildcard DNS + Let's Encrypt TLS).
- **WhatsApp**: WAHA Plus (Sumopod), per-firm session = tenant id.
- **OCR**: Google Document AI (live intake); Foxit Pro + direct extraction (shared corpus, once).
- **LLM**: client-provided key (default rec. Gemini 3.1 Pro); embeddings separate/cheaper.

## Tunables — finalized defaults (T104)

Defaults live in `backend/app/core/config.py` and per-firm `firm_settings`. Current
values (tune at the documented checkpoints):

- **OCR confidence threshold**: `0.80` — below → document flagged `low_confidence` [C-VII].
- **Chunking**: `800` tokens, `120` overlap (research.md R3).
- **Embeddings**: dimension `1536` (R1); model per firm (`firm_settings.embedding_config`,
  e.g. `gemini-embedding-001`). LLM generation model default `models/gemini-2.0-flash`.
- **Retrieval**: `top_k=8` per corpus, pgvector HNSW cosine.
- **Reminder lead points**: `7d, 3d, 1d, 0d` (firm-configurable in Settings).
- **Scheduler (Africa/Cairo)**: reminders at `08:00`, manager reports at `08:30`.

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
