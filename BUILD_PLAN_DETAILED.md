# DETAILED BUILD PLAN — Lawyer Office Management SaaS (AI-Powered, Arabic, Egypt)

> **For Claude Code.** This is the authoritative, FINAL specification. It supersedes any
> earlier plan. It reflects the architecture we converged on after resolving several earlier
> contradictions. Treat Sections 3 (Architecture), 6 (Guardrails), and 9 (Audit logging) as
> a constitution: no phase may violate them. Exact DB column types, library versions, and
> framework specifics are decided in-build by competent engineers — but the data model,
> relationships, screens, CRUD behavior, audit rules, and sequencing below are binding.

---

## 1. Product in one sentence

A per-firm, isolated, AI-assisted lawyer office-management system for Egyptian (civil-law)
firms that turns a firm's own documents + a shared Egyptian-law reference base into a
searchable knowledge base — with summarization, extraction, legal-deadline tracking,
contract analysis, and WhatsApp reminders/reports — where **every AI output passes a
mandatory human review gate** and **every data change is audit-logged with who + when**.

---

## 2. Deployment model (FINAL — resolves all earlier contradictions)

**Two environments, SAME stack (this is what makes the move easy):**

- **DEMO / DEV — home server.** Dummy data ONLY (never real client documents). Used for
  building, showcasing to prospects, and validating the stack. Exposed safely via a tunnel
  (Cloudflare Tunnel / Tailscale), NOT by opening home-router ports.
- **PRODUCTION — VPS** (Hetzner / Hostinger / Contabo). Real data. Proper security, SSL,
  backups. Stood up when the first real firm is onboarded.

**Per-firm isolation = PHYSICAL, not logical.** Each firm gets its OWN isolated instance:
its own Docker stack + its own self-hosted Supabase (its own Postgres DB, Auth, Storage,
pgvector). Firm A and Firm B share no database. This is the isolation model — chosen because
physical isolation is verifiable by a sysadmin (a server/container boundary) rather than
requiring code-level RLS auditing across a shared DB.

> NOTE on RLS: RLS is still used, but now for **role-based access INSIDE one firm's instance**
> (partner vs lawyer vs paralegal vs secretary), NOT for cross-firm tenant isolation. Cross-firm
> isolation is the separate-instance boundary.

**Going home → VPS is a DEPLOYMENT, not a live-data migration** (home holds only dummy data),
so it is low-risk. See Section 11.

---

## 3. Technology stack (FINAL — locked)

| Layer | Choice | Notes |
|---|---|---|
| Frontend / dashboard | **Next.js 14 + TypeScript**, RTL-first (Arabic) | Dashboard only |
| Backend / AI engine | **Python + FastAPI** | All AI, OCR orchestration, embeddings, scheduling |
| DB + Auth + Storage + RAG | **Self-hosted Supabase** (Postgres + GoTrue auth + Storage + **pgvector**) via Docker | One stack per firm. Do NOT use MS SQL Server — it breaks pgvector/RAG. Do NOT split auth to cloud while data is self-hosted — it breaks RLS + integration. |
| Containerization | **Docker + docker-compose** (official Supabase self-host compose) | Same images home & VPS |
| Orchestration | **Portainer** | Manage per-firm stacks |
| Reverse proxy + routing | **Traefik** (or Nginx Proxy Manager) | Subdomain → correct firm container |
| WhatsApp channel | **WAHA Plus** hosted on **Sumopod** (~$0.83/firm/mo) | Reminders, reports, assistant |
| OCR — live intake | **Google Document AI** (Enterprise Document OCR, ~$1.50/1,000 pages) | Automated pipeline for firms' ongoing scanned uploads |
| OCR — shared corpus (one-time) | **Foxit PDF Editor Pro** (already owned) for image files; direct text extraction for text-PDFs | One-time central prep; verify Arabic OCR quality on a sample first, else use Document AI for that batch |
| LLM (generation) | **Client-provided API key.** Recommended default: **Gemini 3.1 Pro**; Claude for accuracy-sensitive; Qwen3 if self-hosted | Inference cost sits with the client, not the platform |
| Embedding model | Decide explicitly whether on client key or platform | Separate, cheaper AI cost than the chat LLM |

**Jurisdiction:** Egyptian civil law. Precedent is **persuasive (استئناس), never binding** —
any precedent/reference feature is *argument support*, never a decision basis or prediction.

---

## 4. Data sources & the two-corpus RAG model

1. **Shared legal-reference corpus (Egyptian public law).** ~10 GB, prepared ONCE centrally,
   embedded ONCE (never per firm). Provided with every firm instance so firms benefit out of
   the box. **Hard line: this layer is PUBLIC LAW ONLY.** No firm/client data ever enters it.
   - Files with selectable text → extract directly (no OCR).
   - Image files → Foxit Pro OCR (one-time) → text → normalize.
   - **Copyright caution:** raw statute text is generally distributable; copyrighted
     commentaries/publisher annotations are NOT — verify rights before redistributing.
   - **Currency/accuracy:** this corpus is a single source of error propagated to all firms —
     keep it authoritative and updatable.
   - **Delivery choice:** either bake the embedded corpus into each instance (simplest, full
     isolation, but re-ship on law updates) OR a central read-only reference service (update
     once; valid because it is public, non-confidential law). Default: central read-only.
2. **Per-firm private corpus.** Each firm's own scanned case documents + its own private
   references. Lives ONLY in that firm's instance. Confidential.

RAG retrieval searches BOTH corpora (private + shared) and passes results to the LLM.

---

## 5. DATA MODEL — logical entities & relationships

Each firm instance has its own copy of this schema. Exact column types decided in-build;
the entities, relationships, and audit fields below are binding.

### Core entities

- **firm_settings** (single row per instance): firm name, locale, WAHA URL + key, LLM API key,
  embedding config, subscription metadata. *This is where infra keys are stored per instance.*
- **users**: id, full_name, email, **role** (`partner_manager` | `lawyer` | `paralegal` |
  `secretary`), status. Auth handled by Supabase GoTrue; this table holds profile + role.
- **cases (matters)**: id, title, client_name, case_number, court, case_type, status,
  created_by, created_at.
- **case_assignments**: case_id → user_id (which lawyer owns/works the case). MANY-to-many.
  Drives "notify the responsible lawyer" and report scoping.
- **documents**: id, case_id, file_path (Supabase Storage), source_type (`text_pdf` |
  `scanned`), **status** (`pending` → `processing` → `ready` | `low_confidence` | `failed`),
  ocr_confidence, uploaded_by, uploaded_at.
- **document_chunks**: id, document_id, chunk_text (normalized Arabic), **embedding (pgvector)**,
  page_ref/source location (for grounding).
- **ai_outputs**: id, document_id/case_id, type (`summary` | `extraction` | `analysis` |
  `clause_flag` | `risk_signal`), content, source_links (grounding → chunks), **review_state**
  (`draft_unreviewed` | `approved`), generated_by_model, created_at, approved_by, approved_at,
  approved_version. *Nothing leaves `draft_unreviewed` without an explicit human approve.*
- **deadlines**: id, case_id, type (`general` | `appeal_istinaf` | `mu3arada` | `naqd`),
  basis (e.g. judgment type/date the suggestion came from), suggested_date, **confirmed**
  (bool), confirmed_by, confirmed_at, responsible_user_id (from case_assignments),
  derived_from_document_id, low_confidence_flag.
- **tasks**: id, case_id, assigned_to, description, due_date, status.
- **notifications_log**: id, deadline_id/task_id, recipient_user_id, channel (`whatsapp`),
  scheduled_for, sent_at, status. *Proof a reminder fired.*
- **reports_log**: id, type (`daily_what_happened` | `tomorrow_tasks`), recipient (manager),
  generated_at, sent_at.
- **references_private**: firm's own uploaded references (chunked + embedded like documents).
- **(shared corpus)**: read-only, central or baked-in (Section 4).
- **audit_log**: see Section 9 — records EVERY create/update/delete.

### Key relationships (logical)
```
firm_settings (1) —— (∞) users
users (∞) —— (∞) cases            via case_assignments
cases (1) —— (∞) documents
documents (1) —— (∞) document_chunks   (chunk holds the pgvector embedding + source ref)
documents/cases (1) —— (∞) ai_outputs  (each AI output links back to its source chunks = grounding)
cases (1) —— (∞) deadlines —— (1) responsible user
deadlines/tasks (1) —— (∞) notifications_log
every mutation on every table —— (1) audit_log entry
```

---

## 6. GUARDRAILS — apply to every phase, no exceptions

- **G1 — Per-firm physical isolation.** Separate instance per firm from day one. Inside an
  instance, RLS enforces role-based access. Never one shared DB across firms.
- **G2 — Mandatory human review gate.** Every `ai_outputs` row is born `draft_unreviewed` and
  CANNOT be exported/printed/attached-as-official/sent-to-client until a human clicks
  **"Reviewed & Approved."**
- **G3 — Approval audit.** On approve, record who + when + which version (in `ai_outputs` and
  `audit_log`).
- **G4 — Source grounding.** Every AI claim links to the exact source chunk/page it came from.
- **G5 — Visual AI marking.** AI text is visibly marked "AI-generated — requires review" until
  approved.
- **G6 — OCR confidence gate.** Outputs from a `low_confidence` scan carry a stronger warning;
  may require double review.
- **G7 — "Assistive tool, not legal advice" posture** in UI copy, AI responses, and ToS.
- **G8 — Deterministic code decides; AI only phrases (time/safety-critical).** Reminders,
  deadline notifications, and scheduled reports are driven by deterministic scheduled code,
  never an autonomous agent. The LLM may only phrase a report's prose. A missed deadline must
  trace to "the row wasn't there," not "the agent decided not to."
- **G9 — Full audit logging.** Every add/edit/delete on every entity is logged (Section 9).
- **G10 — Self-hosting security baseline.** Fresh production secrets, SSL, protected Studio,
  firewall, tested automated backups (Section 12).

---

## 7. AI ARCHITECTURE — three separate components (not "one AI")

- **A — Retriever (application code, NOT the LLM):** embeds the query, searches pgvector
  (private + shared corpora), retrieves relevant chunks. Deterministic code + embedding model.
- **B — LLM (generation):** receives retrieved chunks as context and reasons/writes
  (summary/extraction/analysis). The client's key. Does not search, does not act.
- **C — Orchestrator/Scheduler (deterministic, see G8):** scheduler fires on time → code queries
  confirmed data → sends via WAHA. LLM optionally phrases report text only.

**RAG flow:** question → code embeds + searches pgvector (A) → chunks → LLM generates grounded
answer (B) → output enters `draft_unreviewed` (G2) with source links (G4).

**Notification flow:** scheduler fires → code queries confirmed deadlines/tasks → sends via WAHA
→ writes `notifications_log`. (LLM phrasing optional only.)

**Hybrid agentic policy:** agentic autonomy is allowed for the conversational assistant and
complex analysis (Phases 5–6) only. NEVER for reminders/reports (Phase 4) — see G8.

---

## 8. SCREENS / INTERFACES & CRUD (where data + keys are entered)

RTL Arabic UI. Each screen states which roles can access it (RBAC). CRUD = create/read/
update/delete; EVERY create/update/delete writes an `audit_log` entry (Section 9).

- **Login / Auth screen** — Supabase GoTrue. Per-instance users only.
- **Dashboard (home)** — role-aware overview: upcoming deadlines, documents in `processing`,
  items awaiting review, today's tasks.
- **Cases list + Case detail** — CRUD on cases. Case detail shows documents, AI outputs,
  deadlines, tasks, assignments. **Add/Edit/Delete case**; **assign/unassign lawyers**.
- **Document upload + status** — upload PDF (→ Supabase Storage, row `pending`); shows
  lifecycle status; `low_confidence` documents flagged with a warning banner (G6).
- **AI output review screen** — shows AI content with **AI-marking (G5)** and **source links
  (G4)**; **"Reviewed & Approved"** button (G2/G3). Until approved: cannot export/send.
- **Deadlines screen** — list + detail. Legal appeal deadlines appear as **suggestions
  requiring confirmation** ("Verify & Confirm"); only confirmed deadlines activate notifications.
  **Add/Edit/Delete deadline**; confirm action recorded.
- **Tasks screen** — CRUD on tasks; assign to users; due dates.
- **Conversational assistant** — chat over WhatsApp (WAHA) and/or in-app; RAG-scoped to correct
  case; outputs still pass the review gate.
- **Reports view (manager/partner only, RBAC)** — daily "what happened" + "tomorrow's tasks."
- **Settings / Admin (partner_manager only)** — **this is where keys are entered:** WAHA URL +
  key, LLM API key (client-provided), embedding config, firm profile. **Add/Edit** of keys is
  itself audit-logged (log the action + who + when, NOT the secret value).
- **Users & roles (partner_manager only)** — CRUD on users, assign roles.
- **Audit log viewer (partner_manager only)** — read-only view of the change history.

---

## 9. AUDIT LOGGING — every change, who + when (explicit requirement)

A first-class `audit_log` table records EVERY create, update, and delete across all entities.
Each entry captures:

- **who** — acting user_id (and role)
- **when** — timestamp
- **what** — entity/table + record id
- **action** — `create` | `update` | `delete`
- **change detail** — for updates: field-level old value → new value; for create/delete: the
  record snapshot
- **context** — e.g. which instance/firm, source screen/API endpoint

Rules:
- Secrets (API keys, JWT secrets) are NEVER stored in plaintext in the audit log — log that a
  key was added/changed/removed and by whom, not its value.
- The audit log is **append-only** (no edits/deletes of audit entries) — it is the firm's proof
  of accountability and dispute evidence.
- AI approvals (G3) and deadline confirmations are high-value audit events — capture version too.

---

## 10. BUILD PHASES (sequence is the recommendation)

> Guiding rule: certain value before probabilistic value; review gate ships WITH the first AI
> output; legally sensitive features last; audit logging exists from Phase 0.

- **Phase 0 — Foundation & isolation.** Per-firm instance scaffolding (Docker + self-hosted
  Supabase), RBAC roles, **audit_log from the start (G9)**, users/cases/assignments, document
  upload + status lifecycle, Storage. Exit: isolated instance with auth, roles, audit, uploads.
- **Phase 1 — Document pipeline + quality gate (the spine).** Worker: image pre-process →
  Document AI → **confidence gate (G6)** → **Arabic normalization (mandatory)** → chunk →
  embed → pgvector. Plus one-time shared-corpus prep (Foxit/direct extraction, embed once).
  **⚠️ CHECKPOINT: test Document AI on a real sample of the firm's actual scans BEFORE building
  further — the confidence number gates everything.** Exit: searchable knowledge base.
- **Phase 2 — Summarization & extraction + REVIEW GATE.** One pipeline; ship full review
  workflow (G2/G3), grounding (G4), AI marking (G5) WITH it. Exit: reviewed, audited summaries.
- **Phase 3 — Deadlines, obligations & reports over WhatsApp (deterministic, G8).**
  - 3a — general deadlines/obligations + WAHA reminders (build first).
  - 3c — manager daily reports ("what happened" + "tomorrow"), RBAC-restricted (build second).
  - 3b — legal appeal deadlines (استئناف/معارضة/نقض) as **confirm-required suggestions**, escalating
    WAHA reminders to the responsible lawyer; **forfeiture deadlines — never auto-computed as
    fact; behind a flag; expert lawyer must bless the calculation logic before release** (build last).
- **Phase 4 — Conversational assistant over WhatsApp.** RAG, intent routing, retrieval strictly
  scoped to the correct case; agentic allowed here; outputs pass review gate.
- **Phase 5 — Contract analysis & clause identification.** Clause taxonomy, missing/unusual
  flags, playbook compare; agentic allowed.
- **Phase 6 — Reference/precedent matching (persuasive only).** Across firm's own + shared
  corpus; argument support, never decision basis.
- **Phase 7 — Risk signals (NOT prediction), last & cautious.** Flag concerning clauses /
  missing protections / contradictions already in the document. Clearly assistive (G7).

---

## 11. DEPLOYMENT — home server → VPS (steps & complexity)

Because demo and production run the SAME Docker stack and home holds only dummy data, this is a
**deployment, not a live-data migration** — low-to-moderate complexity, mostly sysadmin work.

1. Provision VPS (Ubuntu); harden (SSH keys, firewall, updates).
2. Install Docker + docker-compose.
3. Deploy the same app + self-hosted Supabase stack (copy compose + build context).
4. Generate FRESH production secrets (new JWT secrets, keys) — never reuse demo secrets.
5. DNS: point domain + wildcard subdomains at the VPS IP (replaces home tunnel).
6. Reverse proxy (Traefik/Nginx) + Let's Encrypt wildcard SSL → routes subdomain → firm container.
7. Enable automated, tested backups per firm DB BEFORE onboarding any real firm.
8. Test with dummy data on the VPS, then onboard the first real firm.

Per-firm provisioning automation (a script that stands up a new firm instance with its keys)
becomes worthwhile after ~3–4 firms — defer, but plan for it. Future VPS→VPS moves of LIVE data
DO require careful pg_dump/restore + storage copy + verified restore (the home→VPS step does not,
since home is dummy data).

---

## 12. SELF-HOSTING SECURITY (mandatory for legal data)

- Replace ALL default secrets (JWT secret especially — defaults let anyone forge tokens).
- SSL everywhere; protect Supabase Studio (do not leave it publicly exposed); firewall.
- Per-firm automated backups, **tested for restore**, not just taken. Losing a firm's case DB is
  catastrophic — backups are non-optional.
- Keep the stack patched.

---

## 13. COST MODEL (per firm / month, approximate)

| Item | ~Cost | Type |
|---|---|---|
| VPS (hosts app + self-hosted Supabase) | ~$15–20 | fixed |
| Database (self-hosted) | $0 | folded into VPS |
| Backup storage | ~$2–5 | fixed |
| WAHA on Sumopod | $0.83 | fixed |
| OCR (Document AI, ~2,000 pages) | ~$3 | variable |
| LLM inference | $0 (client pays) | — |
| Domain (amortized) | ~$1 | fixed |

**Fixed floor ≈ $22–30/firm/month.** One-time costs (archive OCR on onboarding, one-time corpus
embedding) should be billed as a separate **onboarding/setup fee**, not absorbed into the monthly.
**Price on VALUE to the firm (time saved + liability avoided), not cost-plus** — the floor is
small relative to the value; there is large headroom for margin with a large firm.

---

## 14. INSTRUCTIONS TO CLAUDE CODE

1. Start at Phase 0; meet each phase's exit criteria before the next.
2. Sections 3, 6, 9 are inviolable across all phases.
3. Build the audit log (Section 9) in Phase 0 — it is not a later add-on.
4. At the Phase 1 checkpoint, STOP and surface OCR confidence on real scans before proceeding.
5. Build the AI as three separate components (Section 7). Never route reminders/reports through
   an autonomous agent (G8). Agentic autonomy only for assistant + complex analysis (Phases 5–6).
6. Default every AI output to `draft_unreviewed`; no path bypasses the review gate (G2).
7. Phase 3b (legal deadlines): behind a flag; not enabled for users until expert-reviewed.
8. Use PostgreSQL/pgvector via self-hosted Supabase. Do NOT substitute MS SQL Server. Do NOT
   split auth to a separate cloud while data is self-hosted.
9. Where exact schema/library choices are needed, propose them — but flag any choice that should
   wait for the Phase 1 real-data (OCR) result.
10. Keep demo (home) and production (VPS) on the SAME stack so deployment stays a lift-and-shift.
