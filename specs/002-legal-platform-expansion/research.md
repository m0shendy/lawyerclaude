# Phase 0 Research: Legal Platform Expansion

**Date**: 2026-06-08
**Plan**: [plan.md](plan.md)

All spec 001 research decisions (R1–R13) remain in force. This document resolves the
open engineering knobs introduced by the 42 new functional requirements in spec 002. The
locked stack (Next.js 14, FastAPI, self-hosted Supabase + pgvector, Docker/Traefik, WAHA,
Google Document AI, client-key LLM) is unchanged.

---

### R1. Multi-provider LLM abstraction

- **Decision**: Use **LiteLLM** as the provider abstraction layer in `backend/app/llm/providers.py`.
  `firm_settings` gains a `llm_provider_config` JSONB column: `{ "provider": "gemini", "model":
  "models/gemini-2.0-flash", "api_key": "<secret>" }`. LiteLLM translates this to the correct
  SDK call. Provider switching requires only a firm Settings update — no code or image change.
- **Rationale**: LiteLLM is the standard open-source multi-provider proxy that already handles
  Gemini, OpenAI, Claude, Mistral, Cohere, and Azure OpenAI with a single interface. It avoids
  per-provider branching code and is actively maintained. The API key remains a secret —
  audit-logged as action-only, never as value (**[C-III]**).
- **Alternatives**: Custom switch/case per provider (rejected — brittle, high maintenance);
  LangChain LLMs (rejected — heavier dependency for generation-only use case).

---

### R2. Document version storage strategy

- **Decision**: Each checked-in version is stored as a **separate file** in Supabase Storage
  under a versioned path (`docs/<doc_id>/v<N>/<original_filename>`). The `document_versions`
  table holds the version chain: `version_number`, `file_path`, `root_version_id` (the v1 doc),
  `prev_version_id` (the immediate predecessor), `uploaded_by`, `uploaded_at`. Navigation
  traverses the `prev_version_id` chain. The current canonical version is the row with the
  highest `version_number` for a `document_id`.
- **Rationale**: Full copies are simpler and more reliable for legal documents than diffs — no
  reconstruction logic, no diff corruption risk, straightforward audit. Storage cost is
  acceptable at legal-document scale (PDFs/DOCX, not media). Supabase Storage already handles
  per-file access control and audit via Storage policies.
- **Alternatives**: Deltas/diffs (rejected — complex reconstruction, corruption risk for
  PDFs/DOCX); single overwriting file (rejected — violates version-history requirement).

---

### R3. Document check-out pessimistic locking

- **Decision**: A dedicated `document_checkouts` table with a unique index on `document_id`.
  Check-out is an INSERT — if a row already exists, it fails with a constraint error (document
  already checked out by another user). Check-in DELETEs the row and INSERTs a new version.
  Auto-release: a cron job or trigger releases stale checkouts older than 24h (firm-configurable)
  and creates an audit entry. Deactivating a user releases their checkouts immediately.
- **Rationale**: Pessimistic locking is appropriate for legal documents where conflicts are
  costly and the user population is small (firm, not public). The unique index provides a clean
  DB-enforced lock — no application-side race condition.
- **Alternatives**: Optimistic locking with version conflicts (rejected — allows concurrent edits,
  only detecting conflict on merge, which is unacceptable for legal documents); advisory locks
  (rejected — session-scoped, doesn't survive worker restart).

---

### R4. Auto-numbering for CASE, CL, and INV identifiers

- **Decision**:
  - **CASE-XXXX**: `CASE-` prefix + a per-instance Postgres sequence (`cases_number_seq`),
    zero-padded to 4 digits, stored in a generated column or a DEFAULT on `cases.case_number`.
  - **CL-XXXXXX**: `CL-` prefix + `clients_number_seq`, zero-padded to 6 digits.
  - **INV-YYYYMM-XXXXXX**: `INV-` prefix + `YYYYMM` of invoice creation date + a counter
    stored in an `invoice_sequences` helper table keyed on `(year, month)`, incremented
    atomically with `FOR UPDATE`. Zero-padded to 6 digits.
  - All sequences are per-instance (not global across firms) — consistent with per-firm
    physical isolation (**[C-I]**).
- **Rationale**: Postgres sequences are atomic and gap-tolerant (no duplicates even under
  concurrent inserts). The per-year-month INV counter is the standard accounting practice
  for invoice numbering; storing it in a helper table avoids sequence-per-month complexity.
- **Alternatives**: UUID-based identifiers (rejected — not human-readable / not matching
  spec's explicit numbering pattern); application-layer MAX+1 (rejected — race condition).

---

### R5. Conflict check implementation

- **Decision**: Add a `tsvector` search index (`GIN`) on a computed column combining:
  `clients.name`, `client_contacts.name` (for opposing contacts), and
  `cases.opposing_counsel`. When a new client or opposing party is entered, run a
  `plainto_tsquery` search across active matters. Returns matching matter IDs + party names +
  `conflict_check_notes`. Results are surfaced as a warning in the UI — not a hard block
  (the firm may proceed with the conflict disclosed). All conflict-check runs are logged to
  `conflict_check_log` (who, when, query, matches).
- **Rationale**: Full-text search handles name variations and partial matches better than
  exact equality. The `tsvector` index keeps the query fast (sub-3 seconds at 500 matters /
  1,000 contacts per SC-104). Logging all checks satisfies audit requirements.
- **Alternatives**: Exact string matching (rejected — misses "Mohammed" vs "Mohamed" etc.);
  external fuzzy-match service (rejected — over-engineering, network latency, isolation risk).

---

### R6. Analytics KPIs and reporting

- **Decision**:
  - **Dashboard KPIs** (open matters, upcoming hearings/deadlines, pending invoices, AI outputs
    awaiting review): **Materialized views** in Postgres, refreshed by a trigger (or immediate
    `REFRESH MATERIALIZED VIEW CONCURRENTLY`) after each relevant mutation. The dashboard API
    reads the materialized view — never the LLM.
  - **Financial and operational reports**: **On-demand** queries against live tables (no
    materialized caching needed — reports are low-frequency and acceptable at 1–2 second latency
    for a firm-scale dataset).
  - **Activity feed**: Direct query on `audit_log` with a LIMIT and a time filter — no caching.
  - All report assembly is deterministic code; AI MAY phrase narrative summaries of reports
    but never selects or omits items (**[C-IV]**).
- **Rationale**: Materialized views give the dashboard sub-100ms KPI reads without repeatedly
  scanning large tables. On-demand reports are fresh and simple. The activity feed is naturally
  sourced from the append-only audit log (**[C-III]**, **[C-IV]**).
- **Alternatives**: On-demand for all (rejected for KPIs — too slow at peak if tables grow);
  Redis cache (rejected — adds infra dependency; materialized views achieve the same in-DB).

---

### R7. Calendar aggregation strategy

- **Decision**: A Postgres **view** (`calendar_events`) that UNIONs `hearings` and
  `appointments`, each with a `event_type` discriminator column (`hearing` / `appointment`),
  mapped to a common schema: `id`, `event_type`, `title`, `scheduled_at`, `end_at`,
  `matter_id`, `assigned_lawyer_id`, `status`. The API reads this view; no separate table.
  RLS is enforced on the underlying `hearings` and `appointments` tables, so the view
  automatically respects per-role data access.
- **Rationale**: A DB view is the lightest-weight aggregation that keeps calendar reads
  consistent with the live data in both underlying tables. No sync overhead, no duplication.
- **Alternatives**: Application-layer merge of two API calls (rejected — more network overhead,
  harder to paginate / filter consistently); a separate calendar table (rejected — duplication,
  sync complexity).

---

### R8. Client portal authentication model

- **Decision**: The `client` role is a first-class GoTrue role within the firm's Supabase
  instance. A `client` user is created in `auth.users` (GoTrue) by an Admin, linked to a
  `clients` record via `clients.portal_user_id`. JWT claims include `role: client` and
  `client_id: <uuid>`. All portal API routes (`/portal/*`) require `role = client`. RLS
  policies on `matters`, `documents`, `document_sharing`, `invoices`, and `appointments`
  restrict rows to those linked to the authenticated `client_id`. The portal is served from
  the same Next.js instance at `/portal/**` (a route group), behind a role guard.
- **Rationale**: Using the existing GoTrue instance eliminates a second auth service, which
  would conflict with **[C-XII]** (auth MUST NOT be split to a separate cloud service while
  data is self-hosted). The `client` role and RLS policies enforce data scoping without a
  separate database.
- **Alternatives**: Separate auth service for portal (rejected — violates C-XII);
  magic-link only portal (rejected — GoTrue already supports this; no separate service needed).

---

### R9. Document template and letter pack engine

- **Decision**: Templates stored in `document_templates` with a `content_template` field (the
  template body) and a `variables_schema` JSONB (list of variable names and their source path
  in the matter/client data model). Generation is a two-pass process:
  1. **Deterministic pass**: substitute known variables (client name, matter number, court,
     date, etc.) using a Mustache-style engine (server-side string replacement — no LLM).
  2. **AI pass**: fill contextual/substantive text blocks marked `{{AI: description}}` using
     the LiteLLM provider configured for the firm; the output is `draft_unreviewed`, AI-marked,
     with each AI-filled section grounded to relevant source chunks.
  Missing variables produce a clearly marked `[MISSING: var_name]` placeholder (not blank or
  misleading content — per spec edge case).
- **Rationale**: Splitting deterministic vs AI fill makes the AI's contribution explicit and
  auditable; the deterministic variables (name, date, number) are never AI-hallucinated.
  Missing-variable placeholders prevent silent omissions in legal documents.
- **Alternatives**: Pure AI generation with template as context (rejected — deterministic fields
  should never be probabilistic); pure Mustache/no AI (rejected — defeats the letter pack
  generation value proposition).

---

### R10. Hearing reminder scheduling

- **Decision**: Extend the existing spec 001 deterministic scheduler (APScheduler worker) with
  a new job: query `hearings` where `status IN ('scheduled', 'confirmed')` and
  `scheduled_at BETWEEN now() AND now() + reminder_days * interval '1 day'` where
  `reminder_days` is per-hearing (default 3 days). On match, send WAHA notification to
  `hearings.assigned_lawyer_id`'s registered phone, INSERT a `notifications_log` row.
  Escalation: if `scheduled_at` is within 1 day and hearing is still `scheduled` (not confirmed
  by lawyer), also notify a `partner_manager`. Failure handling identical to spec 001 deadline
  reminders — logged and surfaced, never silently dropped (**[C-IV]**).
- **Rationale**: Reusing the existing scheduler component (spec 001 Component C) ensures
  hearing reminders are deterministic and traceable to data — identical guarantees to deadline
  reminders. No new infrastructure needed.
- **Alternatives**: Separate cron service for hearings (rejected — unnecessary duplication);
  event-driven reminders via an agent (explicitly forbidden by **[C-IV]**).
