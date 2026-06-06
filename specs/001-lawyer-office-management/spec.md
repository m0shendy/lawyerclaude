# Feature Specification: AI-Assisted Lawyer Office Management System

**Feature Directory**: `specs/001-lawyer-office-management`
**Created**: 2026-06-05
**Status**: Draft
**Scope**: Whole product (all features, screens, and entities) in a single specification, with
requirements tagged by priority so planning can slice the work.
**Input**: Per-firm, isolated, AI-assisted office-management system for Egyptian law firms that
turns a firm's own documents plus a shared Egyptian-law reference base into a searchable
knowledge base, with AI assistance behind a mandatory human review gate.

> **Constitution binding**: This spec is subordinate to the project constitution
> (`.specify/memory/constitution.md`). Where this spec and the constitution appear to conflict,
> the constitution wins and the conflict must be surfaced, not silently resolved. Key
> constitutional anchors are referenced inline as **[C-I]** … **[C-XII]**.

---

## Clarifications

### Session 2026-06-05

- Q: Who may approve an AI output (release it from `draft_unreviewed`)? →
  **A: The lawyer assigned to that case, or any partner_manager.** Paralegals and secretaries
  may create and view drafts but may not approve.
- Q: How is a WhatsApp contact tied to a firm user? →
  **A: Each user has a pre-registered, verified phone number in their profile.** Inbound
  assistant queries are answered only when the sender matches a known active user, and replies
  and retrieval scope follow that user's role and case assignments.
- Q: How do deadline/obligation reminders escalate? →
  **A: Escalating reminders at decreasing lead times to the responsible lawyer; if still
  unacknowledged near the due date, also notify a partner_manager.**
- Q: What does this spec cover? → **A: The whole product as one spec**, with requirements
  grouped by prioritized user story.

---

## User Scenarios & Testing *(mandatory)*

Roles: **partner_manager**, **lawyer**, **paralegal**, **secretary**. "Manager" = partner_manager.

### User Story 1 — Onboard a firm instance with roles, audit, and document intake (Priority: P1)

A new firm receives its own isolated instance. The manager signs in, configures the firm
profile, creates user accounts with roles, and the team begins uploading scanned case
documents and tracking matters. Every change is recorded in an append-only audit log from
day one.

**Why this priority**: Nothing else can exist without an isolated instance, authenticated
role-based users, the audit log, cases, and the document-intake lifecycle. This is the
foundation (Constitution **[C-I]**, **[C-III]**).

**Independent Test**: Provision one instance, create one user of each role, create a case,
assign a lawyer, upload a document, and confirm (a) only that instance's users can log in,
(b) role-based screen access is enforced, (c) the document progresses through its status
lifecycle, and (d) every create/update/delete produced an audit-log entry with who/when/
what/old→new.

**Acceptance Scenarios**:

1. **Given** a fresh firm instance, **When** the manager creates a lawyer account and assigns
   the `lawyer` role, **Then** that user can log in and see only role-permitted screens, and an
   audit-log entry records the creation (who, when, record, action).
2. **Given** a logged-in lawyer, **When** they create a case and assign themselves, **Then** the
   case appears in their case list and an audit-log entry is written for both the create and the
   assignment.
3. **Given** a logged-in user, **When** they upload a PDF to a case, **Then** a document row is
   created in `pending`, the file is stored, and the row advances through
   `processing` → `ready` (or `low_confidence` / `failed`).
4. **Given** a user from Firm A, **When** they attempt to authenticate against Firm B's
   instance, **Then** access is denied (cross-firm isolation is the instance boundary).
5. **Given** any record is edited, **When** the change is saved, **Then** the audit log captures
   field-level old→new values and cannot be edited or deleted afterward.

---

### User Story 2 — Document summarization & key-point extraction behind the review gate (Priority: P1)

A user opens a ready document and requests an AI summary plus extraction of key points
(parties, dates, claims, amounts). The output is created as a draft, visibly marked
AI-generated, with each claim linked to its source location. It cannot be exported, printed,
attached as official, or sent until the assigned lawyer or a partner approves it.

**Why this priority**: This is the first and primary unit of AI value, and it must ship
*together* with the full review gate, source grounding, and AI marking (Constitution **[C-II]**,
**[C-V]**, **[C-VI]**). It is the template every later AI feature follows.

**Independent Test**: Run summarization+extraction on a ready document; verify the output is
`draft_unreviewed`, visibly AI-marked, every claim links to a source chunk/page, export/send is
blocked until approval, and approval is recorded with who/when/version.

**Acceptance Scenarios**:

1. **Given** a `ready` document, **When** a user requests a summary, **Then** an `ai_output` of
   type `summary` is created in `draft_unreviewed`, marked "AI-generated — requires review."
2. **Given** an extraction output, **When** the user inspects any extracted item (party, date,
   claim, amount), **Then** each item links to the exact source chunk/page it came from.
3. **Given** a `draft_unreviewed` output, **When** any user attempts to export/print/attach/send
   it, **Then** the action is blocked.
4. **Given** an output derived from a `low_confidence` document, **When** it is displayed,
   **Then** it carries a stronger warning and is marked as requiring heightened review
   (Constitution **[C-VII]**).
5. **Given** a `draft_unreviewed` output, **When** the assigned lawyer or a partner clicks
   "Reviewed & Approved," **Then** `review_state` becomes `approved` and who/when/approved
   version are recorded in the output and the audit log. A paralegal or secretary attempting the
   same is denied.

---

### User Story 3 — Deadlines & obligations with escalating WhatsApp reminders (Priority: P2)

A user records a deadline or obligation on a case with a due date and a responsible lawyer.
Deterministic scheduled code sends WhatsApp reminders to that lawyer at decreasing lead times;
if the deadline is unacknowledged as it approaches, a partner is also notified. Every send is
logged.

**Why this priority**: Time-critical value that depends only on the foundation. Reminders are
driven by deterministic scheduled code, never an agent (Constitution **[C-IV]**).

**Independent Test**: Create a confirmed deadline with a responsible lawyer and a future due
date; advance time across the reminder lead points and verify each reminder is sent to the
correct WhatsApp number, escalation to a partner occurs when unacknowledged, and each send
writes a `notifications_log` row.

**Acceptance Scenarios**:

1. **Given** a deadline with a responsible lawyer and due date, **When** a reminder lead time is
   reached, **Then** a WhatsApp reminder is sent to that lawyer's registered number and a
   `notifications_log` entry records recipient/channel/scheduled_for/sent_at/status.
2. **Given** an unacknowledged deadline approaching its due date, **When** the final lead time is
   reached, **Then** a partner_manager is also notified.
3. **Given** a deadline notification, **When** the responsible lawyer's number is missing or
   invalid, **Then** the failure is logged with status and surfaced for follow-up (no silent
   drop).
4. **Given** the scheduler, **When** it fires, **Then** it queries stored, confirmed data only —
   a missed reminder is always traceable to data, never to an agent's judgment.

---

### User Story 4 — Manager daily reports over WhatsApp (Priority: P2)

Each day, the manager receives two WhatsApp reports: "what happened today" and "tomorrow's
tasks," scoped to the firm. Report content is assembled by deterministic code from stored data;
an AI may only phrase the prose.

**Why this priority**: High-value managerial visibility built on the same deterministic
scheduler. Restricted to managers (RBAC).

**Independent Test**: With sample activity and tasks, trigger the daily report job and verify
the manager receives both reports over WhatsApp, the figures match stored data, and a
`reports_log` entry is written. Confirm non-managers cannot access the Reports view.

**Acceptance Scenarios**:

1. **Given** a day with activity, **When** the daily report job runs, **Then** the manager
   receives a "what happened today" report whose items reconcile to audited stored events, and a
   `reports_log` row is written.
2. **Given** tasks due tomorrow, **When** the job runs, **Then** the manager receives a
   "tomorrow's tasks" report listing them.
3. **Given** an AI phrasing step, **When** it runs, **Then** it only rewords code-selected
   facts; it never selects, adds, or omits which items appear.
4. **Given** a non-manager, **When** they attempt to open the Reports view, **Then** access is
   denied.

---

### User Story 5 — Legal appeal-deadline suggestions (confirm-required, flagged) (Priority: P3)

For appeal deadlines (istinaf / mu'arada / naqd), the system may *propose* a suggested date
derived from a document, but it never treats the date as fact. No notification activates until
the responsible lawyer clicks "Verified & Confirmed." The feature stays behind a flag and is
disabled until an expert lawyer has blessed the calculation logic.

**Why this priority**: Highest legal risk (forfeiture). Ships last and stays behind a flag
(Constitution **[C-X]**).

**Independent Test**: With the flag enabled in a test instance, generate an appeal-deadline
suggestion; verify it is inert (no notifications) until "Verified & Confirmed," that
confirmation records who/when, and that with the flag off the feature is invisible to users.

**Acceptance Scenarios**:

1. **Given** the feature flag is off, **When** any user uses the system, **Then** appeal-deadline
   suggestions are not available.
2. **Given** the flag is on and a judgment document, **When** a suggestion is generated, **Then**
   a deadline of type `appeal_istinaf`/`mu'arada`/`naqd` is created as a suggestion with its
   basis and `derived_from_document_id`, `confirmed = false`, sending no notification.
3. **Given** an unconfirmed appeal suggestion, **When** the due date passes, **Then** no
   reminder is sent (it never activated).
4. **Given** an appeal suggestion, **When** the responsible lawyer clicks "Verified &
   Confirmed," **Then** `confirmed = true` with confirmed_by/at recorded, and only then do
   reminders schedule.
5. **Given** a suggestion derived from a `low_confidence` document, **When** displayed, **Then**
   it carries the heightened warning.

---

### User Story 6 — Conversational case assistant over WhatsApp (Priority: P3)

A pre-registered user messages the firm's WhatsApp assistant in natural language and asks a
question about a case. The assistant retrieves from the firm's private corpus and the shared
Egyptian-law corpus, answers with grounded source links, and scopes results to the user's role
and assigned cases. Any drafted output still passes the review gate before it can be treated as
official.

**Why this priority**: High value but depends on the document pipeline and identity model.
Agentic autonomy is permitted here (Constitution **[C-IV]**), but grounding and the review gate
still apply.

**Independent Test**: From a registered user's number, ask a case question over WhatsApp;
verify the answer is grounded with source links, scoped to that user's assigned cases, and that
an unregistered number is refused.

**Acceptance Scenarios**:

1. **Given** a registered active user's number, **When** they ask a question over WhatsApp,
   **Then** the assistant answers using retrieval over the private + shared corpora with source
   links to exact locations.
2. **Given** a user without access to a case, **When** they ask about it, **Then** the assistant
   does not reveal that case's content.
3. **Given** an unregistered or inactive sender, **When** they message the assistant, **Then**
   they are refused.
4. **Given** any assistant-produced artifact intended for official use, **When** created,
   **Then** it is `draft_unreviewed` and AI-marked until approved.
5. **Given** any answer, **When** it cites the shared corpus, **Then** it is framed as
   persuasive reference (istishhad), never as binding precedent or outcome prediction
   (Constitution **[C-IX]**).

---

### User Story 7 — Contract analysis & clause identification (Priority: P4)

A user runs contract analysis on a document. The system identifies clauses against a taxonomy,
flags missing or unusual clauses, and can compare against a playbook. Findings are AI outputs:
grounded, AI-marked, and behind the review gate.

**Why this priority**: Advanced analysis value; depends on the pipeline and review gate.

**Independent Test**: Analyze a contract; verify clauses are identified against the taxonomy,
missing/unusual clauses are flagged with source links, and findings are `draft_unreviewed`
until approved.

**Acceptance Scenarios**:

1. **Given** a contract document, **When** analysis runs, **Then** `ai_output`s of type
   `clause_flag`/`analysis` are produced identifying clauses by taxonomy, each grounded to source.
2. **Given** a playbook comparison, **When** run, **Then** missing or unusual clauses are flagged
   relative to the playbook.
3. **Given** any finding, **When** displayed, **Then** it is AI-marked and cannot be
   exported/sent until approved by the assigned lawyer or a partner.

---

### User Story 8 — Reference/precedent matching, persuasive only (Priority: P4)

A user finds references across the firm's own corpus and the shared Egyptian-law corpus that
support an argument. Results are framed strictly as persuasive support — never a decision basis
or outcome prediction.

**Why this priority**: Useful argument support; lower urgency and legally sensitive framing.

**Independent Test**: Request references for a legal point; verify matches come from both
corpora with source links and are presented as persuasive support with the appropriate
disclaimer.

**Acceptance Scenarios**:

1. **Given** a legal point, **When** reference matching runs, **Then** results from the private
   and shared corpora are returned with source links.
2. **Given** any reference result, **When** displayed, **Then** it is labeled persuasive
   (istishhad) and explicitly not a binding precedent or prediction (Constitution **[C-IX]**).
3. **Given** the shared corpus, **When** anything is written, **Then** no firm or client data is
   ever added to it (public law only).

---

### User Story 9 — Risk signals on existing content, not prediction (Priority: P5)

A user reviews risk signals that flag concerning clauses, missing protections, or
contradictions *already present* in a document. The system never predicts case outcomes.

**Why this priority**: Last and most cautious; highest misuse risk if framed as prediction.

**Independent Test**: Run risk signals on a document with a known problematic clause; verify it
is flagged with a source link and explicitly framed as an observation about existing content,
not a prediction.

**Acceptance Scenarios**:

1. **Given** a document with a problematic or missing-protection clause, **When** risk signals
   run, **Then** an `ai_output` of type `risk_signal` flags it with a source link.
2. **Given** any risk signal, **When** displayed, **Then** it describes existing content only and
   carries the assistive-tool / not-legal-advice posture (Constitution **[C-VIII]**).
3. **Given** any risk signal, **When** displayed, **Then** it is AI-marked and behind the review
   gate.

---

### Edge Cases

- A document that fails OCR enters `failed`; the user is shown why and no AI output is generated
  from it.
- A `low_confidence` document still allows AI output, but every derived output carries the
  heightened warning and may require double review.
- A responsible lawyer with no registered/valid phone number: reminders log a failure and
  surface for follow-up rather than silently dropping.
- A deadline whose responsible lawyer is unassigned or removed: surfaced as needing reassignment;
  reminders do not silently vanish.
- An AI output is approved, then its source document is later replaced/updated: the approved
  version is retained as approved; a new draft is required for the new content.
- An unconfirmed appeal-deadline suggestion is never allowed to trigger any notification.
- A secret value (API key) is changed in Settings: the audit log records the action + who + when,
  never the value (Constitution **[C-III]**).
- A user is deactivated: they can no longer log in or query the WhatsApp assistant.
- Concurrent edits to the same record: each saved change is independently audit-logged.

---

## Requirements *(mandatory)*

### Functional Requirements

**Isolation, identity & access (P1)**

- **FR-001**: Each firm MUST run as its own fully isolated instance; users of one firm MUST NOT
  be able to authenticate against or access another firm's instance. **[C-I]**
- **FR-002**: The system MUST authenticate users per instance and assign each a role of
  `partner_manager`, `lawyer`, `paralegal`, or `secretary`.
- **FR-003**: The system MUST enforce role-based access to every screen and action; manager-only
  screens (Reports, Settings/Admin, Users & Roles, Audit Log viewer) MUST be inaccessible to
  other roles.
- **FR-004**: Each user profile MUST hold a verified WhatsApp phone number used for reminders,
  reports, and assistant identity.

**Audit logging (P1)**

- **FR-005**: Every create, update, and delete on every entity MUST write an audit-log entry
  capturing who (user + role), when, what (entity + record id), action, and field-level
  old→new values (or a record snapshot for create/delete). **[C-III]**
- **FR-006**: The audit log MUST be append-only; entries MUST NOT be editable or deletable.
- **FR-007**: Secret values (API keys, WAHA key) MUST NEVER be stored in the audit log; only the
  action, who, and when MUST be recorded.
- **FR-008**: AI approvals and deadline confirmations MUST be recorded as high-value audit events
  including the version approved/confirmed.

**Cases, documents & pipeline (P1)**

- **FR-009**: Users MUST be able to create, read, update, and delete cases and assign/unassign
  lawyers (many-to-many) to them.
- **FR-010**: Users MUST be able to upload documents to a case; an uploaded document MUST be
  created in `pending` and progress through `processing` → `ready` | `low_confidence` |
  `failed`, recording `ocr_confidence`, `source_type`, and uploader/time.
- **FR-011**: The system MUST process documents into normalized-Arabic chunks with a source
  reference (page/location) suitable for grounding, and make them searchable.
- **FR-012**: Retrieval MUST search both the firm's private corpus and the shared Egyptian-law
  reference corpus.
- **FR-013**: The shared Egyptian-law corpus MUST be read-only and contain public law only; no
  firm or client data may ever be written into it. **[C-I]**

**AI outputs & the review gate (P1)**

- **FR-014**: Every AI output MUST be created in `review_state = draft_unreviewed`. **[C-II]**
- **FR-015**: A `draft_unreviewed` output MUST NOT be exportable, printable, attachable as
  official, or sendable to a client by any code path. **[C-II]**
- **FR-016**: Every AI output MUST be visibly marked "AI-generated — requires review" until
  approved. **[C-VI]**
- **FR-017**: Every AI claim/item MUST link to the exact source location it was derived from.
  **[C-V]**
- **FR-018**: Only the lawyer assigned to the case or a partner_manager MAY approve an AI output;
  paralegals and secretaries MUST NOT be able to approve. *(Clarified 2026-06-05.)*
- **FR-019**: On approval, the system MUST set `review_state = approved` and record approved_by,
  approved_at, and approved version. **[C-II]**, **[C-III]**
- **FR-020**: Outputs derived from a `low_confidence` document MUST carry a stronger warning and
  MAY require double review. **[C-VII]**

**Summarization & extraction (P1)**

- **FR-021**: Users MUST be able to generate a document summary and an extraction of key points
  (parties, dates, claims, amounts) as a single feature, each item grounded to source.

**Deadlines, obligations & reminders (P2)**

- **FR-022**: Users MUST be able to create, read, update, and delete deadlines and obligations on
  a case, each with a due date and a responsible lawyer.
- **FR-023**: Reminders MUST be sent by deterministic scheduled code, never by an autonomous
  agent. **[C-IV]**
- **FR-024**: Reminders MUST escalate at decreasing lead times to the responsible lawyer, and if
  the item remains unacknowledged near its due date, MUST also notify a partner_manager.
  *(Clarified 2026-06-05.)*
- **FR-025**: Every reminder attempt MUST write a `notifications_log` entry with recipient,
  channel, scheduled_for, sent_at, and status; failures MUST be logged and surfaced, never
  silently dropped.

**Manager daily reports (P2)**

- **FR-026**: The system MUST send the manager two daily WhatsApp reports — "what happened today"
  and "tomorrow's tasks" — assembled deterministically from stored data, with an AI permitted to
  phrase prose only (never to select/add/omit items). **[C-IV]**
- **FR-027**: Each report send MUST write a `reports_log` entry; the Reports view MUST be
  manager-only.

**Legal appeal-deadline suggestions (P3)**

- **FR-028**: Appeal deadlines (`appeal_istinaf` | `mu'arada` | `naqd`) MUST be created only as
  suggestions with their basis and source document; the system MUST NEVER treat a computed
  appeal deadline as fact. **[C-X]**
- **FR-029**: An appeal-deadline suggestion MUST send no notification and MUST remain inert until
  the responsible lawyer clicks "Verified & Confirmed," which records confirmed_by/at. **[C-X]**
- **FR-030**: The appeal-deadline feature MUST stay behind a feature flag and MUST remain
  disabled for users until an expert lawyer has blessed the calculation logic. **[C-X]**

**Conversational assistant (P3)**

- **FR-031**: The assistant MUST answer natural-language case questions over WhatsApp using
  retrieval over the private + shared corpora, with grounded source links.
- **FR-032**: The assistant MUST only respond to senders whose number matches a known active
  user, and MUST scope retrieval and answers to that user's role and assigned cases.
  *(Clarified 2026-06-05.)*
- **FR-033**: Any assistant artifact intended for official use MUST pass the review gate
  (`draft_unreviewed` + AI marking) before being treated as official. **[C-II]**

**Contract analysis, references & risk signals (P4–P5)**

- **FR-034**: Contract analysis MUST identify clauses against a taxonomy, flag missing/unusual
  clauses, and support playbook comparison, producing grounded, AI-marked outputs behind the
  review gate.
- **FR-035**: Reference/precedent matching MUST return results from both corpora framed strictly
  as persuasive support (istishhad), never as binding precedent or outcome prediction. **[C-IX]**
- **FR-036**: Risk signals MUST flag concerning clauses, missing protections, or contradictions
  already present in a document, MUST never predict outcomes, and MUST carry the
  assistive-tool / not-legal-advice posture. **[C-VIII]**, **[C-IX]**

**Settings, users & cross-cutting posture**

- **FR-037**: Managers MUST be able to enter and update firm settings — WAHA URL/key, LLM API
  key, embedding config, and firm profile — with key add/edit audit-logged as action + who
  (never the secret value). **[C-III]**
- **FR-038**: Managers MUST be able to create, read, update, and delete users and assign roles.
- **FR-039**: Managers MUST have a read-only audit-log viewer over the change history.
- **FR-040**: UI copy, AI responses, and the Terms of Service MUST plainly state that this is an
  assistive tool and that professional judgment and responsibility remain with the lawyer.
  **[C-VIII]**
- **FR-041**: The dashboard MUST present a role-aware overview including upcoming deadlines,
  documents in processing, items awaiting review, and today's tasks.
- **FR-042**: Users MUST be able to create, read, update, and delete tasks, assign them to users,
  and set due dates.

### Key Entities

- **firm_settings** — one row per instance: firm profile, WAHA URL/key, LLM API key, embedding
  config, subscription metadata. (Holds secrets; never logged as values.)
- **users** — id, full name, email, verified phone, role, status. Authenticated per instance.
- **cases (matters)** — client name, case number, court, type, status, created_by/at.
- **case_assignments** — many-to-many users↔cases; drives "responsible lawyer" notifications and
  report scope.
- **documents** — case_id, file path, source_type (text_pdf | scanned), status (pending →
  processing → ready | low_confidence | failed), ocr_confidence, uploaded_by/at.
- **document_chunks** — document_id, normalized-Arabic chunk text, vector embedding, source
  reference (page/location) for grounding.
- **ai_outputs** — type (summary | extraction | analysis | clause_flag | risk_signal), content,
  source_links (grounding), review_state (draft_unreviewed | approved), model, approved_by/at,
  approved_version.
- **deadlines** — case_id, type (general | appeal_istinaf | mu'arada | naqd), basis,
  suggested_date, confirmed, confirmed_by/at, responsible_user_id, derived_from_document_id,
  low_confidence_flag.
- **tasks** — case_id, assigned_to, description, due_date, status.
- **notifications_log** — deadline/task reference, recipient, channel, scheduled_for, sent_at,
  status. (Proof a reminder fired.)
- **reports_log** — type, recipient, generated_at, sent_at.
- **references_private** — firm's own uploaded references (chunked + embedded like documents).
- **shared corpus** — read-only Egyptian public-law reference base; no firm/client data.
- **audit_log** — append-only record of every create/update/delete: who, when, what, action,
  old→new.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of AI outputs are created in `draft_unreviewed`; 0% can be exported, printed,
  attached as official, or sent before an authorized approval. (No bypass path exists.)
- **SC-002**: 100% of create/update/delete actions across all entities produce an audit-log
  entry; 0% of audit entries can be edited or deleted after the fact.
- **SC-003**: 0 instances of a firm user accessing another firm's data (verified by the instance
  boundary).
- **SC-004**: 100% of AI claims/items presented to a reviewer carry a working link to their exact
  source location.
- **SC-005**: 0 secret values appear anywhere in the audit log; 100% of key changes are recorded
  as action + who + when.
- **SC-006**: 100% of confirmed deadlines with a valid responsible-lawyer number generate the
  scheduled escalating reminders, and 100% of reminder attempts (success or failure) are logged.
- **SC-007**: 0 appeal-deadline suggestions trigger a notification before "Verified & Confirmed,"
  and the feature is invisible to users while its flag is off.
- **SC-008**: 100% of WhatsApp assistant responses are returned only to pre-registered active
  users and are scoped to the sender's assigned cases; unregistered senders receive 0 case
  content.
- **SC-009**: A manager who reconciles a daily report against the audit log finds 100% of report
  items backed by stored, audited events (no AI-invented items).
- **SC-010**: 100% of outputs derived from a `low_confidence` document display the heightened
  warning.
- **SC-011**: 100% of reference/precedent and risk-signal outputs display the persuasive-only /
  not-prediction / assistive-tool framing.
- **SC-012**: A new firm instance can be brought to a working state (auth, roles, audit,
  document upload) and a first document uploaded and processed without any cross-firm data
  sharing.

---

## Assumptions

- The reminder/report/assistant messaging channel is WhatsApp (via the firm's configured WAHA
  endpoint), as established by the product input and build plan.
- The interface is Arabic, right-to-left, per the project's established direction.
- "Manager" privileges map to the `partner_manager` role; manager-only screens are Reports,
  Settings/Admin, Users & Roles, and the Audit Log viewer.
- The shared Egyptian-law corpus is prepared and embedded once centrally and provided read-only
  to each instance; keeping it authoritative/current is an operational responsibility.
- LLM inference uses the firm-provided API key configured in Settings; embedding configuration is
  likewise firm-configurable.
- Default reminder lead points (e.g., 7/3/1/same-day) are a sensible starting default; exact
  values may be tuned during planning.
- "Tasks due tomorrow" and "what happened today" use the firm's local timezone/day boundary.
- Standard web-application expectations apply for performance, error handling, and session
  management unless stated otherwise.

## Dependencies

- A configured WhatsApp/WAHA endpoint and key per firm (entered in Settings).
- A firm-provided LLM API key and embedding configuration (entered in Settings).
- The centrally prepared shared Egyptian-law reference corpus, available read-only to the
  instance.
- Per-instance authentication and storage for documents.
- (Appeal-deadline feature) Expert-lawyer sign-off on calculation logic before its flag is
  enabled for users.

## Out of Scope (this spec)

- Outcome prediction of any kind (explicitly prohibited — see risk signals / references).
- Cross-firm analytics or any shared store of firm/client data.
- Billing/time-tracking, e-filing/court-system integrations, and client-facing portals (not in
  the provided feature set).
- The deployment/hosting and security-baseline procedures themselves (governed by the
  constitution and build plan; this spec assumes a provisioned, secured instance).
