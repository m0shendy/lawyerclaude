# Tasks: AI-Assisted Lawyer Office Management System

**Feature Directory**: `specs/001-lawyer-office-management`
**Plan**: [plan.md](plan.md) · **Spec**: [spec.md](spec.md) · **Data model**: [data-model.md](data-model.md) · **Contracts**: [contracts/](contracts/)
**Constitution**: [.specify/memory/constitution.md](../../.specify/memory/constitution.md) (v1.0.0)

> **Phase order is mandated by the build plan and reaffirmed by the user.** A **HARD STOP**
> checkpoint (T052) follows the document pipeline: Google Document AI must be validated on real
> scan samples before any later phase. Reminders/reports are **deterministic, never agentic**
> (**[C-IV]**). Every AI output is born `draft_unreviewed` (**[C-II]**); every mutation is
> audit-logged append-only (**[C-III]**).

**Legend**: `[P]` = parallelizable (different files, no incomplete deps). `[USn]` = serves user
story n. Setup/Foundational/Checkpoint/Polish tasks carry no story label.

**Paths** follow plan.md layout: `frontend/`, `backend/app/{api,retriever,llm,scheduler,pipeline,audit,core,models}`, `backend/workers/`, `supabase/migrations/`, `infra/{traefik,provision,backup,security}`, `shared-corpus/`.

---

## Phase 1: Setup & Infrastructure Scaffolding

- [X] T001 Create the monorepo structure (`frontend/`, `backend/`, `supabase/`, `infra/`, `shared-corpus/`) per plan.md
- [X] T002 [P] Initialize Next.js 14 + TypeScript app with RTL-first Arabic config in `frontend/`
- [X] T003 [P] Initialize FastAPI app + dependency management (pyproject) with skeleton in `backend/app/main.py`
- [X] T004 [P] Author the per-firm Docker stack (Supabase self-host + backend + worker + frontend) in `infra/docker-compose.yml`
- [X] T005 [P] Configure Traefik reverse proxy with subdomain routing + wildcard DNS + Let's Encrypt TLS in `infra/traefik/`
- [X] T006 [P] Create the per-firm provisioning script skeleton that generates FRESH secrets (never defaults) in `infra/provision/provision_firm.sh` **[C-XI]**
- [X] T007 [P] Create the security-baseline scripts (host firewall, Supabase Studio protection) in `infra/security/` **[C-XI]**
- [X] T008 [P] Create the per-firm automated backup + restore-test script in `infra/backup/backup_restore_test.sh` **[C-XI]**
- [X] T009 [P] Set up linting/formatting/test harness for `frontend/` and `backend/`

---

## Phase 2: Foundational (BLOCKING prerequisites — must complete before any user story)

**Builds the schema, the audit log (now, not later), auth, and RBAC core that every story needs.**

- [X] T010 Create migration: enable `pgvector` + base extensions in `supabase/migrations/0001_extensions.sql` **[C-XII]**
- [X] T011 Create migration: core schema for all 13 entities (firm_settings, users, cases, case_assignments, documents, document_chunks, ai_outputs, deadlines, tasks, notifications_log, reports_log, references_private) in `supabase/migrations/0002_core_schema.sql`
- [X] T012 Create migration: HNSW (cosine) vector index on `document_chunks.embedding` in `supabase/migrations/0003_vector_index.sql`
- [X] T013 Create migration: append-only `audit_log` table (who/role/when/entity/record/action/old→new/context) in `supabase/migrations/0004_audit_log.sql` **[C-III]**
- [X] T014 Create migration: audit triggers on every audited table capturing field-level old→new with secret-column redaction in `supabase/migrations/0005_audit_triggers.sql` **[C-III]**
- [X] T015 Create migration: `REVOKE UPDATE, DELETE` on `audit_log`; grant app roles INSERT-only (append-only enforcement) in `supabase/migrations/0006_audit_append_only.sql` **[C-III]**
- [X] T016 Create migration: RLS policies for **in-instance** roles (partner_manager/lawyer/paralegal/secretary) in `supabase/migrations/0007_rls_roles.sql` **[C-I]**
- [X] T017 Create migration: review-gate DB guard — `ai_outputs.review_state` defaults `draft_unreviewed`; export/official-send reads filter `approved` in `supabase/migrations/0008_review_gate.sql` **[C-II]**
- [X] T018 Implement backend config + secrets loading in `backend/app/core/config.py`
- [X] T019 [P] Implement DB connection/session in `backend/app/core/db.py`
- [X] T020 [P] Implement GoTrue/JWT auth + user+role resolution dependency in `backend/app/core/security.py`
- [X] T021 [P] Implement server-side RBAC dependency/decorator in `backend/app/core/rbac.py` **[C-I]**
- [X] T022 [P] Implement per-instance feature-flag accessor (reads `firm_settings`) in `backend/app/core/flags.py`
- [X] T023 [P] Implement entity models (pydantic + db) for all entities in `backend/app/models/`
- [X] T024 [P] Implement audit-write helper + verification used by services/triggers in `backend/app/audit/audit.py` **[C-III]**
- [X] T025 Implement auth endpoints `/auth/login`, `/auth/logout`, `/me` (per-instance users; inactive rejected) in `backend/app/api/auth.py`
- [X] T026 [P] Implement frontend Supabase client + auth context in `frontend/lib/supabase.ts`
- [X] T027 [P] Implement frontend RBAC route guards in `frontend/lib/rbac.ts` **[C-I]**
- [X] T028 [P] Implement app shell + RTL layout + persistent `<Disclaimer/>` (assistive tool / not legal advice) in `frontend/app/layout.tsx` and `frontend/components/Disclaimer.tsx` **[C-VIII]**
- [X] T029 [P] Implement shared `<AiMarkedOutput/>` and `<ReviewGate/>` component shells in `frontend/components/` **[C-II][C-V][C-VI]**
- [X] T030 [P] Implement the Login screen in `frontend/app/login/`

**Checkpoint**: schema + audit triggers + RLS + auth + shared UI in place. User stories can begin.

---

## Phase 3: User Story 1 — Foundation & Isolation (Priority: P1) 🎯 MVP

**Goal**: An isolated instance with role-based users, audited CRUD on cases/assignments, and the
document upload + status lifecycle.
**Independent test**: Create one user per role, a case, an assignment, upload a document; verify
in-instance RBAC, the document status lifecycle, cross-firm login denial, and an audit entry for
every change (quickstart §4).

- [X] T031 [US1] Implement users service + endpoints (manager CRUD, assign roles, activate/deactivate) in `backend/app/api/users.py`
- [X] T032 [P] [US1] Implement cases model→service→endpoints (CRUD) in `backend/app/api/cases.py`
- [X] T033 [P] [US1] Implement case_assignments endpoints (assign/unassign, many-to-many) in `backend/app/api/assignments.py`
- [X] T034 [US1] Implement document upload endpoint → Supabase Storage, row created `pending` in `backend/app/api/documents.py`
- [X] T035 [US1] Implement document status lifecycle endpoints (`pending`→`processing`→`ready`/`low_confidence`/`failed`) in `backend/app/api/documents_lifecycle.py`
- [X] T036 [US1] Implement read-only audit-log viewer endpoint `/audit-log` (manager only) in `backend/app/api/audit.py`
- [X] T037 [P] [US1] Build Users & Roles screen (manager) in `frontend/app/users/`
- [X] T038 [P] [US1] Build Cases list + Case detail screens (CRUD, assign/unassign) in `frontend/app/cases/`
- [X] T039 [P] [US1] Build Document upload + status screen (low_confidence warning banner) in `frontend/app/documents/` **[C-VII]**
- [X] T040 [P] [US1] Build role-aware Dashboard (upcoming deadlines, processing docs, items awaiting review, today's tasks) in `frontend/app/dashboard/`
- [X] T041 [P] [US1] Build read-only Audit log viewer screen (manager) in `frontend/app/audit/`
- [X] T042 [US1] Run the isolation + audit smoke test (per quickstart §4) and record results

---

## Phase 4: Document Processing Pipeline + Confidence Gate (serves US2; shared AI foundation)

**Goal**: Turn uploaded documents into searchable, normalized, embedded chunks with a confidence
gate; prepare the shared corpus once.
**Independent test**: Upload a real scan; verify it flows preprocess → Document AI → confidence
gate → Arabic normalization → chunk → embed → `ready`/`low_confidence`/`failed`, with source refs.

- [X] T043 [US2] Implement the background worker entrypoint (separate image entrypoint) in `backend/workers/pipeline_worker.py`
- [X] T044 [US2] Implement image pre-processing step in `backend/app/pipeline/preprocess.py`
- [X] T045 [US2] Implement Google Document AI (Enterprise Document OCR) client in `backend/app/pipeline/ocr_documentai.py`
- [X] T046 [US2] Implement the confidence gate (mean confidence < threshold → `low_confidence`; hard error → `failed`; store `ocr_confidence`) in `backend/app/pipeline/confidence.py` **[C-VII]**
- [X] T047 [US2] Implement mandatory Arabic normalization (unify alef forms, ta-marbuta, strip diacritics/tatweel, alef-maqsura, clean artifacts) in `backend/app/pipeline/normalize_ar.py`
- [X] T048 [US2] Implement chunking (~800 tokens / ~120 overlap, paragraph-aware, persist page_ref) in `backend/app/pipeline/chunk.py` **[C-V]**
- [X] T049 [US2] Implement embedding client (uses `firm_settings.embedding_config`) writing `document_chunks.embedding` in `backend/app/pipeline/embed.py`
- [X] T050 [US2] Wire pipeline orchestration (status transitions + audit) in `backend/app/pipeline/run.py`
- [X] T051 [P] [US2] Implement the one-time central shared-corpus prep tool (Foxit/extract → normalize → embed ONCE; public law only; read-only) in `shared-corpus/prepare_corpus.py` **[C-I]**

---

## 🚦 CHECKPOINT (HARD STOP) — Validate OCR before proceeding

- [X] T052 **[BLOCKING]** Validate Google Document AI confidence on a real sample of the firm's actual scans; inspect `ocr_confidence`, tune the threshold (T046), and obtain explicit go-ahead. **No task in Phase 5 or later may start until this passes.** (quickstart §5, **[C-VII]**) — ✅ CLEARED 2026-06-06: 97% confidence on قانون رقم 10 لسنة 2004 بإصدار قانون إنشاء محاكم الأسرة.PDF, status=جاهز

---

## Phase 5: User Story 2 — Summarization & Extraction behind the Review Gate (Priority: P1)

**Goal**: Generate grounded summaries + key-point extraction as `draft_unreviewed`, AI-marked
outputs that cannot leave the gate until an assigned lawyer or partner approves.
**Independent test**: Summarize a `ready` document; verify draft state, AI marking, per-claim
source links, export blocked until approval, approval restricted to assigned-lawyer/manager, and
heightened warning on `low_confidence` source (quickstart §6).

- [X] T053 [US2] Implement the Retriever (component A): embed query + pgvector search across private + shared corpora in `backend/app/retriever/retrieve.py` **[C-V]**
- [X] T054 [US2] Implement the LLM generation client (component B, client API key, generation only) in `backend/app/llm/generate.py`
- [X] T055 [US2] Implement the `ai_outputs` service: create `draft_unreviewed` with `source_links` grounding in `backend/app/api/ai_outputs.py` **[C-II][C-V]**
- [X] T056 [US2] Implement summarize + extraction endpoint `/documents/{id}/summarize` (parties/dates/claims/amounts) in `backend/app/api/ai_outputs.py`
- [X] T057 [US2] Propagate `low_confidence_flag` from source document to derived outputs in `backend/app/api/ai_outputs.py` **[C-VII]**
- [X] T058 [US2] Implement approve endpoint (assigned lawyer or manager only; sets `approved` + approved_by/at/version; paralegal/secretary → 403) in `backend/app/api/ai_outputs.py` **[C-II][C-III]**
- [X] T059 [US2] Implement export/official-send endpoint that rejects anything not `approved` (no bypass) in `backend/app/api/ai_outputs.py` **[C-II]**
- [X] T060 [P] [US2] Build the AI output review screen (AI marking + source links + "Reviewed & Approved" + disabled export until approved) in `frontend/app/ai-review/` **[C-II][C-V][C-VI]**
- [X] T061 [P] [US2] Wire `<AiMarkedOutput/>` + `<ReviewGate/>` behavior incl. heightened low-confidence warning in `frontend/components/`
- [X] T062 [US2] Run the review-gate + grounding test (quickstart §6) and record results

---

## Phase 6: User Story 3 — Deadlines/Obligations + WhatsApp Reminders (Priority: P2) — *build 3a first*

**Goal**: Track general deadlines/obligations and tasks; deterministic scheduler sends escalating
WhatsApp reminders to the responsible lawyer, escalating to a partner if unacknowledged.
**Independent test**: Create a confirmed deadline + responsible lawyer; advance time and verify
reminders at each lead point, partner escalation, and a `notifications_log` row per attempt
(quickstart §7).

- [X] T063 [US3] Implement deadlines model→service→endpoints (general type, CRUD, responsible lawyer) in `backend/app/api/deadlines.py`
- [X] T064 [P] [US3] Implement tasks CRUD (assign + due dates) in `backend/app/api/tasks.py`
- [X] T065 [US3] Implement the deterministic scheduler worker (component C) entrypoint in `backend/workers/scheduler_worker.py` **[C-IV]**
- [X] T066 [US3] Implement the WAHA WhatsApp client (per-firm session) in `backend/app/scheduler/waha.py`
- [X] T067 [US3] Implement reminder escalation logic (7d/3d/1d/same-day → responsible lawyer; escalate to partner if unacknowledged) reading firm-configurable lead points in `backend/app/scheduler/reminders.py` **[C-IV]**
- [X] T068 [US3] Write `notifications_log` for every attempt incl. `failed`/`skipped` (never silently drop) in `backend/app/scheduler/reminders.py`
- [X] T069 [P] [US3] Build Deadlines screen + Tasks screen in `frontend/app/deadlines/` and `frontend/app/tasks/`
- [X] T070 [US3] Run the reminder delivery + escalation test (quickstart §7) and record results — ✅ 22 unit/logic tests pass (`tests/test_phase6_smoke.py`); live WAHA delivery deferred to a provisioned instance (integration test skipped, see quickstart §7)

---

## Phase 7: User Story 4 — Manager Daily Reports over WhatsApp (Priority: P2) — *build 3c second*

**Goal**: Deterministically assembled daily "what happened today" + "tomorrow's tasks" sent to
the manager; the LLM only phrases prose.
**Independent test**: With sample activity, run the report job; verify both reports reach the
manager, items reconcile to audited data, a `reports_log` row is written, non-managers are denied.

- [X] T071 [US4] Implement deterministic daily report assembly (selects events/tasks from stored, audited data) in `backend/app/scheduler/reports.py` **[C-IV]**
- [X] T072 [US4] Implement LLM phrasing-only step (rewords code-selected facts; cannot add/omit/select items) in `backend/app/scheduler/reports.py` **[C-IV]**
- [X] T073 [US4] Send via WAHA + write `reports_log` in `backend/app/scheduler/reports.py` (also `GET /reports/daily` in `backend/app/api/reports.py`; daily job wired into `workers/scheduler_worker.py`)
- [X] T074 [P] [US4] Build the Reports view (manager only) in `frontend/app/reports/`
- [X] T075 [US4] Run the report reconciliation test (items ↔ audit log) and record results — `backend/tests/test_phase8_reports.py` (unit-level: items carry `audit_id`; live-DB integration still pending)

---

## Phase 8: User Story 5 — Legal Appeal-Deadline Suggestions (Priority: P3) — *build 3b LAST, behind a flag*

**Goal**: Appeal deadlines (istinaf/mu'arada/naqd) appear only as confirm-required suggestions,
behind a feature flag (default off), inert until "Verified & Confirmed", and disabled for users
until an expert lawyer blesses the calculation logic.
**Independent test**: With the flag on, generate a suggestion; verify no notification until
confirmed, confirmation records who/when, and with the flag off the feature is invisible.

- [ ] T076 [US5] Gate the feature on `firm_settings.feature_appeal_deadlines` (default **false**) in `backend/app/core/flags.py` and UI **[C-X]**
- [ ] T077 [US5] Implement appeal-deadline suggestion generation (`confirmed=false`, `basis`, `derived_from_document_id`, never treated as fact, no notification) in `backend/app/api/deadlines.py` **[C-X]**
- [ ] T078 [US5] Implement confirm endpoint `/deadlines/{id}/confirm` (responsible lawyer → `confirmed=true` → only now schedule reminders) in `backend/app/api/deadlines.py` **[C-X]**
- [ ] T079 [US5] Enforce no notification while unconfirmed + heightened warning on low-confidence source in `backend/app/scheduler/reminders.py` **[C-X][C-VII]**
- [ ] T080 [P] [US5] Build the appeal-deadline UI as confirm-required suggestions (hidden unless flag on; "Verify & Confirm" action) in `frontend/app/deadlines/` **[C-X]**
- [ ] T081 [US5] Add expert sign-off gate: document the blessing requirement, keep the flag off until obtained, and add the ToS note that deadline calculation is the lawyer's responsibility **[C-X][C-VIII]**

---

## Phase 9: User Story 6 — Conversational Case Assistant over WhatsApp (Priority: P3)

**Goal**: A pre-registered user queries the firm assistant in natural language; retrieval is
strictly scoped to that user's role + assigned cases, answers are grounded, and official
artifacts still pass the review gate. Agentic autonomy is allowed here.
**Independent test**: From a registered user's number, ask a case question; verify grounded,
scoped answer; unregistered/inactive sender refused; non-assigned case content withheld.

- [ ] T082 [US6] Implement the WAHA inbound webhook handler in `backend/app/api/assistant.py`
- [ ] T083 [US6] Implement sender phone → active user identity binding (refuse unknown/inactive) in `backend/app/api/assistant.py` **[C-I]**
- [X] T084 [US6] Implement retrieval scoped to caller role + `case_assignments` in `backend/app/retriever/scoped.py` **[C-I]**
- [X] T085 [US6] Implement the agentic assistant flow (grounded answer with source links; persuasive-only framing; assistive posture) in `backend/app/llm/assistant.py` **[C-V][C-VIII][C-IX]**
- [X] T086 [US6] Route any official-use artifact into `draft_unreviewed` (review gate still applies) in `backend/app/api/assistant.py` **[C-II]** (via `POST /assistant/query` `save_as_draft`)
- [X] T087 [P] [US6] Build the in-app conversational assistant screen in `frontend/app/assistant/`
- [ ] T088 [US6] Run the identity-scope test (unregistered refused; cross-case content blocked) and record results

---

## Phase 10: User Story 7 — Contract Analysis & Clause Identification (Priority: P4)

**Goal**: Identify clauses against a taxonomy, flag missing/unusual clauses, and compare to a
playbook — producing grounded, AI-marked outputs behind the review gate. Agentic allowed.
**Independent test**: Analyze a contract; verify taxonomy clause IDs, missing/unusual flags with
source links, and that findings are `draft_unreviewed` until approved.

- [ ] T089 [US7] Implement clause taxonomy + contract analysis service in `backend/app/llm/contract_analysis.py`
- [ ] T090 [US7] Implement missing/unusual clause flags + playbook comparison in `backend/app/llm/contract_analysis.py`
- [ ] T091 [US7] Implement endpoint `/documents/{id}/analyze-contract` → `clause_flag`/`analysis` outputs (grounded, gated) in `backend/app/api/ai_outputs.py` **[C-II][C-V]**
- [ ] T092 [P] [US7] Extend the AI review UI to render contract-analysis findings (gated) in `frontend/app/ai-review/`

---

## Phase 11: User Story 8 — Reference/Precedent Matching, Persuasive Only (Priority: P4)

**Goal**: Surface references from the private + shared corpora framed strictly as persuasive
support (istishhad) — never binding precedent or outcome prediction.
**Independent test**: Request references for a legal point; verify matches from both corpora with
source links and persuasive-only labeling.

- [ ] T093 [US8] Implement reference matching service across private + shared corpora in `backend/app/retriever/references.py` **[C-IX]**
- [ ] T094 [US8] Apply persuasive-only (istishhad) framing + explicit not-binding / not-prediction labels in `backend/app/retriever/references.py` **[C-IX]**
- [ ] T095 [P] [US8] Build the reference-results UI with the persuasive disclaimer in `frontend/app/` (references view) **[C-IX]**

---

## Phase 12: User Story 9 — Risk Signals on Existing Content, Not Prediction (Priority: P5)

**Goal**: Flag concerning clauses, missing protections, or contradictions already present in a
document — never predicting outcomes — as gated, AI-marked outputs with assistive posture.
**Independent test**: Run risk signals on a document with a known problematic clause; verify it is
flagged with a source link, framed as an observation about existing content, gated.

- [ ] T096 [US9] Implement risk-signal detection over existing document content (no prediction) in `backend/app/llm/risk_signals.py` **[C-VIII][C-IX]**
- [ ] T097 [US9] Implement endpoint `/documents/{id}/risk-signals` → `risk_signal` outputs (grounded, gated, posture text) in `backend/app/api/ai_outputs.py` **[C-II][C-VIII]**
- [ ] T098 [P] [US9] Build the risk-signals UI with assistive-tool / not-prediction posture in `frontend/app/`

---

## Phase 13: Polish & Cross-Cutting Concerns

- [ ] T099 [P] Finalize ToS + UI copy stating "assistive tool, not legal advice" across UI, AI responses, and ToS **[C-VIII]**
- [ ] T100 [P] Write the home→VPS deployment runbook (lift-and-shift, FRESH prod secrets, DNS, wildcard SSL) in `infra/` **[C-XI]**
- [ ] T101 Execute and document a per-firm backup **restore test** before any real onboarding in `infra/backup/` **[C-XI]**
- [ ] T102 [P] Harden the per-firm provisioning script for repeatability (worthwhile after ~3–4 firms) in `infra/provision/`
- [ ] T103 [P] Performance pass: confirm OCR/embedding stay async/background; check retrieval latency at scale
- [ ] T104 [P] Update `CLAUDE.md` and `quickstart.md` with finalized thresholds, lead points, and embedding model/dimension

---

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)** block everything.
- **US1 (Phase 3)** is the MVP and depends only on Foundational.
- **Pipeline (Phase 4)** depends on Foundational (schema, storage, pgvector) and US1 (documents exist).
- **🚦 T052 HARD STOP** blocks Phases 5–12 entirely. Nothing AI-derived proceeds until OCR is validated.
- **US2 (Phase 5)** depends on the Pipeline + checkpoint.
- **US3 (Phase 6)** depends on Foundational (deadlines/tasks/notifications schema) + scheduler; independent of US2.
- **US4 (Phase 7)** depends on US3 scheduler/WAHA infrastructure.
- **US5 (Phase 8)** depends on US3 (reminder infra) and is built LAST among Phase 3 items, behind a flag.
- **US6 (Phase 9)** depends on the Pipeline + Retriever (US2) + review gate.
- **US7 (Phase 10)**, **US8 (Phase 11)**, **US9 (Phase 12)** depend on the Pipeline + Retriever + review gate; otherwise independent of each other.
- **Polish (Phase 13)** is last; T101 (tested restore) must precede onboarding any real firm.

### Story completion order

US1 → (Pipeline + CHECKPOINT) → US2 → US3 → US4 → US5 → US6 → US7 → US8 → US9.

---

## Parallel Execution Examples

- **Setup**: T002–T009 can run in parallel (distinct files/dirs).
- **Foundational**: after migrations T010–T017, the core modules T019–T024 and frontend shells
  T026–T030 are parallelizable.
- **US1**: T032, T033 (cases/assignments), and UI screens T037–T041 run in parallel once T031
  (users) lands.
- **US2**: T060 and T061 (UI) parallel to backend T053–T059 wiring.
- **US3**: T064 (tasks) parallel to deadline/scheduler work; T069 (UI) parallel.
- **Cross-story**: US7, US8, US9 backends (T089–T098) can be staffed in parallel after US2.

---

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + Phase 3 (US1)**: an isolated, audited, role-based instance with
  cases, assignments, and the document upload + status lifecycle. Independently demoable.
- **Increment 1**: Pipeline (Phase 4) → **STOP at T052** → US2 (Phase 5). This delivers the first
  AI value *with* the full review gate, grounding, and AI marking — the template all later AI
  features follow.
- **Increment 2**: US3 + US4 (deterministic deadlines/reminders/reports).
- **Increment 3**: US5 (appeal deadlines, flagged, expert-blessed) — legally sensitive, last in
  Phase 3.
- **Increment 4+**: US6 (assistant), then US7/US8/US9 (analysis, references, risk signals).
- **Before any real firm**: complete T101 (tested per-firm restore) and the security baseline.

## Constitution traceability (selected)

- **[C-II]** review gate: T017, T055, T058, T059, T060, T086, T091, T097.
- **[C-III]** audit append-only: T013–T015, T024, T036, T058.
- **[C-IV]** deterministic reminders/reports: T065, T067, T071, T072.
- **[C-V]** grounding: T048, T053, T055, T060, T085.
- **[C-VII]** OCR confidence gate: T046, T052, T057, T079.
- **[C-X]** appeal deadlines: T076–T081.
- **[C-XI]** self-hosting baseline: T006–T008, T100, T101.
