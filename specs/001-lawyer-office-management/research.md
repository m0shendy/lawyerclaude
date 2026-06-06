# Phase 0 Research: AI-Assisted Lawyer Office Management System

**Date**: 2026-06-05
**Plan**: [plan.md](plan.md)

The stack itself is fixed by the user (Next.js 14, FastAPI, self-hosted Supabase + pgvector,
Docker/Traefik/Portainer, WAHA, Google Document AI, client-key LLM). This document resolves the
remaining *open knobs* that the spec/plan left to engineering judgment. Each is a decision with
rationale and alternatives; values marked **(tune at Phase 1 checkpoint)** may change once real
Arabic scans are measured.

---

### R1. Embedding model & dimensionality

- **Decision**: Use a multilingual, Arabic-capable embedding model accessed via the client's key
  family where possible (separate, cheaper than the chat LLM). Default target dimension **1536**
  (store as `vector(1536)`); make the model + dimension a `firm_settings.embedding_config` value
  so an instance can switch without schema change *for the same dimension*.
- **Rationale**: Egyptian legal Arabic needs strong Arabic coverage; embedding cost is separate
  and far lower than generation, so it can run platform-side or client-side per firm config.
- **Alternatives**: English-centric embeddings (rejected — weak Arabic); a single shared
  dimension hard-coded (rejected — config-driven is more flexible). Changing dimension later
  requires re-embedding; treat dimension as fixed-per-instance.

### R2. pgvector index type

- **Decision**: **HNSW** index on `document_chunks.embedding` with cosine distance.
- **Rationale**: Better recall/latency at our scale (tens of thousands of chunks per firm) and no
  training step; good default for read-heavy RAG.
- **Alternatives**: IVFFlat (needs `lists` tuning + a training set, recall sensitive to data
  growth) — rejected as default; exact scan (too slow as corpus grows).

### R3. Chunking strategy

- **Decision**: Token-aware chunks of **~800 tokens with ~120-token overlap**, split on paragraph
  boundaries after Arabic normalization; persist `page_ref`/location per chunk for grounding.
  **(tune at Phase 1 checkpoint)**
- **Rationale**: Balances retrieval precision with enough context for legal passages; overlap
  avoids splitting a clause across a boundary.
- **Alternatives**: Fixed-character chunks (rejected — breaks Arabic words/clauses); whole-page
  chunks (rejected — too coarse for grounding).

### R4. Document AI confidence gate threshold

- **Decision**: Treat mean OCR confidence **< 0.80** as `low_confidence`; **hard failure** (no
  text extracted / processor error) → `failed`. Store raw `ocr_confidence`. **(tune at Phase 1
  checkpoint — this number gates everything; validate on real firm scans first.)**
- **Rationale**: The build plan makes this the spine checkpoint; a conservative default protects
  downstream AI quality. **[C-VII]**
- **Alternatives**: No gate (rejected — violates C-VII); higher threshold (risks blocking usable
  scans) — defer until measured.

### R5. Arabic normalization ruleset (mandatory)

- **Decision**: Deterministic normalization before chunking: unify alef forms (أ إ آ → ا),
  ta-marbuta handling (ة/ه policy consistent), strip tashkeel/diacritics, normalize alef-maqsura
  (ى/ي), remove tatweel (ـ), collapse whitespace, strip OCR artifacts/control chars, normalize
  digits policy. Applied identically to documents, private references, queries, and the shared
  corpus so vectors are comparable.
- **Rationale**: Consistent normalization is required for reliable Arabic retrieval; it must be
  the same on both sides of the embedding.
- **Alternatives**: Skip normalization (rejected — guarantees retrieval misses); ML-based
  normalization (rejected — nondeterministic, unnecessary).

### R6. Audit capture mechanism

- **Decision**: **Database triggers** write `audit_log` rows on INSERT/UPDATE/DELETE for every
  audited table, capturing acting user + role (from session/JWT claims), timestamp, table,
  record id, action, and JSON old→new diff. `REVOKE UPDATE, DELETE` on `audit_log` from all app
  roles (append-only). Secret columns are redacted in the trigger (log "changed", not value).
- **Rationale**: Triggers cannot be bypassed by an application code path — the strongest way to
  honor "every change, no exceptions" and append-only. **[C-III]**
- **Alternatives**: App-layer logging (rejected — bypassable, the constitution forbids gaps);
  Postgres logical decoding (rejected — heavier, less direct field-diffs).

### R7. Review-gate enforcement

- **Decision**: Defense in depth — `ai_outputs.review_state` defaults `draft_unreviewed`; a
  **DB check/guard** prevents export/official-send pathways from reading non-`approved` rows, and
  **API endpoints** for export/print/attach/send reject anything not `approved`. Approval sets
  `approved_by/at/version` and is a high-value audit event.
- **Rationale**: "No code path may bypass" requires enforcement below the UI. **[C-II]**
- **Alternatives**: UI-only gating (rejected — bypassable).

### R8. Deterministic scheduler

- **Decision**: A dedicated **background worker** (separate entrypoint of the backend image)
  running a deterministic scheduler (APScheduler-style or cron-driven) that, on fire, queries
  **confirmed** deadlines/tasks and sends via WAHA, writing `notifications_log`. The LLM is
  invoked only to phrase report prose, never to decide sends. **[C-IV]**
- **Rationale**: Time/safety-critical actions must be deterministic and traceable to data.
- **Alternatives**: Agent-driven reminders (explicitly forbidden by C-IV); cron in OS only
  (rejected — harder to log/test per firm).

### R9. Reminder escalation lead points

- **Decision**: Default lead points **7d / 3d / 1d / same-day** to the responsible lawyer; if a
  deadline remains unacknowledged at the **1d/same-day** point, also notify a `partner_manager`.
  Lead points stored in `firm_settings` (firm-configurable). **(tune per firm)**
- **Rationale**: Matches the clarified escalation policy (FR-024) and the build plan's "escalating
  reminders."
- **Alternatives**: Single reminder (rejected per clarification); fixed non-configurable schedule
  (rejected — firms differ).

### R10. Feature flag mechanism (appeal deadlines)

- **Decision**: A per-instance flag in `firm_settings` (e.g., `feature_appeal_deadlines = false`
  by default). The appeal-deadline UI and suggestion generation are gated on it; it stays off
  until an expert lawyer blesses the calculation logic. **[C-X]**
- **Rationale**: The most legally dangerous feature must default off and be explicitly enabled.
- **Alternatives**: Build-time flag (rejected — need per-firm runtime control); always-on
  (rejected — violates C-X).

### R11. Shared corpus delivery

- **Decision**: Default to a **central read-only reference service** for the shared Egyptian-law
  corpus (embedded once centrally; updated once on law changes), with the option to bake the
  embedded corpus into an instance for full isolation. Either way it is **public law only** and
  **read-only**; no firm/client data ever enters it. **[C-I]**
- **Rationale**: Central read-only avoids re-shipping ~10 GB on every law update while staying
  valid because the data is public and non-confidential. Baked-in remains available where strict
  isolation is preferred.
- **Alternatives**: Re-embed per firm (rejected — wasteful, error-prone); writable shared store
  (rejected — would allow firm data to leak in, violating C-I).

### R12. WhatsApp identity binding

- **Decision**: Map inbound sender number → an **active** `users` row with a **verified phone**;
  refuse unknown/inactive senders; scope assistant retrieval and answers to that user's role +
  `case_assignments`. The firm's WAHA session is the tenant identifier. **(FR-032)**
- **Rationale**: Honors per-firm isolation and in-instance RBAC over the chat channel. **[C-I]**
- **Alternatives**: Shared-number, unscoped access (rejected per clarification — weak isolation).

### R13. Deployment topology & secrets

- **Decision**: Identical `docker-compose` on home (demo, dummy data, Cloudflare Tunnel) and VPS
  (prod). Per-firm provisioning script generates **fresh** GoTrue/JWT secrets per instance,
  registers the subdomain + Traefik route + wildcard TLS, and configures the WAHA session. Studio
  is network-restricted + auth-protected; host firewall on; per-firm backups taken **and tested
  for restore** before onboarding. **[C-XI]**
- **Rationale**: Same-stack parity makes promotion a lift-and-shift; the security baseline is
  mandatory for legal data.
- **Alternatives**: Different demo vs prod stacks (rejected — breaks lift-and-shift); reusing demo
  secrets in prod (rejected — forbidden by C-XI).
