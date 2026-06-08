# Feature Specification: Legal Platform Expansion

**Feature Directory**: `specs/002-legal-platform-expansion`
**Created**: 2026-06-07
**Status**: Partially implemented — frontend components delivered 2026-06-08; backend + DB migration tasks remain per tasks.md
**Scope**: Expands the existing platform with client management, a full document management
system (DMS with versioning & check-in/out), billing & invoicing, hearing management,
appointment scheduling, a unified calendar, client portal, analytics & reporting, and six
new AI-assistance features (document drafting, contract review, submission drafting, letter
pack generation, case timeline generation, and knowledge search). Also adds multi-provider
LLM configuration.

> **Constitution binding**: This spec is subordinate to the project constitution
> (`.specify/memory/constitution.md`). Constitutional anchors are referenced inline as
> **[C-I]** … **[C-XII]**. Where this spec and the constitution conflict, the constitution
> wins and the conflict must be surfaced.
>
> **Foundation spec**: This expansion builds on and extends
> [specs/001-lawyer-office-management/spec.md](../001-lawyer-office-management/spec.md).
> All requirements from spec 001 remain in force and are not repeated here unless extended.

---

## Clarifications

### Q1 — Language Scope: RESOLVED (2026-06-08)

**Decision**: **Option A — Arabic remains the sole UI language**, consistent with the locked
stack ("RTL-first Arabic"). Multi-language support (English/Spanish/French) is out of scope
for this feature and requires a separate, explicit stack change request if ever needed.

### Q2 — Role Taxonomy: RESOLVED (2026-06-08)

**Decision**: **Option A — Extend existing roles.** The roles partner_manager, lawyer,
paralegal, and secretary are kept unchanged. A new `client` role is added for portal-only
access. No migration of spec 001 is required.

| Role            | Change   | Scope                                                   |
|-----------------|----------|---------------------------------------------------------|
| partner_manager | existing | Full access, settings, staff management (Admin in UI)   |
| lawyer          | existing | Case management, documents, AI features                 |
| paralegal       | existing | Limited access per assigned permissions                 |
| secretary       | existing | Limited access per assigned permissions                 |
| client          | **new**  | Portal access only, restricted to own matters/documents |

---

## User Scenarios & Testing *(mandatory)*

Roles: **partner_manager**, **lawyer**, **paralegal**, **secretary** (all existing), plus
new **client** (portal-only). "Manager" = partner_manager.

---

### User Story 1 — AI-Assisted Legal Document Generation (Priority: P1)

A lawyer opens a matter and requests AI generation of a legal document — a contract, court
submission (مذكرة دفاع), engagement letter, or professional letter. The system generates a
draft using the firm's configured LLM, visibly marks it AI-generated, and creates it in
`draft_unreviewed` state. The lawyer reviews, edits if needed, approves, and then exports
or sends the document.

**Why this priority**: Core new AI value; must ship with the full review gate, grounding,
and AI marking from the first deployment (Constitution **[C-II]**, **[C-V]**, **[C-VI]**).

**Independent Test**: Generate a contract draft and a court submission on a test matter;
verify they are born `draft_unreviewed`, AI-marked, blocked from export/send until approved,
and approval is audit-logged with who/when/version.

**Acceptance Scenarios**:

1. **Given** a matter with context, **When** a lawyer requests an AI document draft, **Then**
   a document is created in `draft_unreviewed`, visibly marked "AI-generated — requires
   review," and export/client-send is blocked.
2. **Given** a `draft_unreviewed` AI document, **When** the assigned lawyer or a
   partner_manager approves it, **Then** `review_state` becomes `approved` and who/when/version
   are audit-logged; paralegals and secretaries are denied approval.
3. **Given** an LLM provider configured in Settings (Gemini, OpenAI, Claude, Mistral, Cohere,
   or Azure OpenAI), **When** generation runs, **Then** the document is produced via that
   provider without requiring system code changes.
4. **Given** an AI-drafted document that cites legal authority, **When** displayed, **Then**
   the citation is framed as persuasive support (استشهاد), never as binding precedent or
   outcome prediction (**[C-IX]**).
5. **Given** a generation request derived from a `low_confidence` source document, **When**
   the draft is displayed, **Then** it carries the heightened OCR-confidence warning (**[C-VII]**).

---

### User Story 2 — AI Contract Review and Risk Flagging (Priority: P1)

A lawyer uploads or opens a contract and triggers an AI contract review. The system analyzes
the document, identifies clause types against a taxonomy, flags missing or unusual clauses,
highlights potential risks, and optionally compares against a firm playbook. Each finding is
grounded to its source location, AI-marked, and held in `draft_unreviewed` until the assigned
lawyer approves.

**Why this priority**: High-value analysis feature; review gate, source grounding, and AI
marking are required from first delivery (Constitution **[C-II]**, **[C-V]**, **[C-VI]**).

**Independent Test**: Run contract review on a contract with known missing clauses; verify
each finding is grounded with source location, AI-marked, blocked from export until approved,
and approved findings are audit-logged.

**Acceptance Scenarios**:

1. **Given** a contract document, **When** AI review runs, **Then** clause findings and risk
   flags are produced — each grounded to the exact source location it was derived from.
2. **Given** a playbook comparison request, **When** run, **Then** missing or unusual clauses
   are flagged relative to the playbook.
3. **Given** a risk flag, **When** displayed, **Then** it describes existing content only —
   it does not predict case outcomes (**[C-VIII]**, **[C-IX]**).
4. **Given** any review finding, **When** displayed, **Then** it is AI-marked and blocked
   from export/print/client-send until the assigned lawyer or a partner_manager approves it.
5. **Given** a review based on a `low_confidence` document, **When** displayed, **Then**
   findings carry the heightened warning (**[C-VII]**).

---

### User Story 3 — Client Management with Conflict Check (Priority: P1)

Staff and lawyers create and manage client records — individuals and organizations — with
auto-generated client numbers, multiple typed contacts, conflict-check notes, and full
history. The built-in conflict check alerts when a prospective new client or opposing party
appears in any existing active matter for the firm.

**Why this priority**: Foundational entity that matters, billing, and the client portal all
depend on. Conflict checking is a professional obligation.

**Independent Test**: Create an individual client and an organization client; attempt to add
a client already listed as opposing counsel in an active matter; verify the conflict alert
fires and conflict notes are displayed.

**Acceptance Scenarios**:

1. **Given** a new client intake, **When** the record is saved, **Then** a unique client number
   (CL-000001 pattern) is auto-generated and client type (individual/organization) is recorded.
2. **Given** a client record, **When** multiple contacts are added, **Then** each is typed
   (primary, billing, opposing, witness) and stored independently.
3. **Given** a new client or opposing-party entry, **When** conflict check runs, **Then** the
   system compares against all active matter parties and alerts on any match, displaying
   conflict notes.
4. **Given** any client create/update/delete, **When** saved, **Then** an audit-log entry
   records who/when/what/old→new (**[C-III]**).

---

### User Story 4 — Document Management with Version Control and Check-In/Out (Priority: P1)

A team organizes matter-related documents in folder hierarchies with full version history,
check-in/check-out to prevent simultaneous edit conflicts, access control levels,
confidentiality flags, a template library, and selective client sharing via the portal.

**Why this priority**: Core DMS capability required for the document-centric workflow of
all matters; version control prevents data loss.

**Independent Test**: Upload a document, check it out (block others from editing), edit and
check in a new version; verify the prior version is preserved; mark a second document
confidential; share a third with a client; verify portal access respects those settings.

**Acceptance Scenarios**:

1. **Given** a document, **When** a user checks it out, **Then** it is locked to that user
   and no other user can check it out simultaneously.
2. **Given** a checked-out document edited and checked in, **When** the check-in completes,
   **Then** a new version is created and all prior versions remain accessible.
3. **Given** a document with access level `restricted`, **When** a user without the required
   role attempts to open it, **Then** access is denied.
4. **Given** a document marked confidential, **When** a client user navigates to it in the
   portal, **Then** access is denied regardless of sharing settings.
5. **Given** a document template, **When** a user generates a new document from it, **Then**
   a pre-populated draft is created and linked to the matter.
6. **Given** a document explicitly shared with a client, **When** that client views the portal,
   **Then** the document is visible to them (and only them among portal users).

---

### User Story 5 — Billing & Invoicing (Priority: P2)

Lawyers and managers generate invoices for client matters with auto-generated invoice numbers,
service line items (description, quantity, unit price), configurable tax and discount, and
payment recording. Invoices progress through a defined lifecycle and clients can view their
own invoices from the portal.

**Why this priority**: Revenue-critical operational function; supports client portal and
financial reporting.

**Independent Test**: Create a draft invoice with multiple line items and a tax rate; send
it; record a partial payment; verify status transitions (Draft → Pending → Partial), each
transition is audit-logged, and the client sees it in the portal.

**Acceptance Scenarios**:

1. **Given** a matter and client, **When** an invoice is created, **Then** a unique invoice
   number (INV-YYYYMM-000001 pattern) is auto-generated with status `draft`.
2. **Given** line items are added, **When** tax and discount are applied, **Then** subtotal,
   tax amount, discount, and total due calculate automatically.
3. **Given** an invoice, **When** a payment is recorded, **Then** payment method (cash, bank
   transfer, cheque, electronic wallet, card), amount, date, and reference are captured and
   invoice status updates to `partial` or `paid`.
4. **Given** any invoice create/update/payment action, **When** saved, **Then** an audit-log
   entry is written (**[C-III]**).
5. **Given** a client portal user, **When** they view invoices, **Then** only invoices issued
   to them are visible.

---

### User Story 6 — Hearing Management (Priority: P2)

Lawyers and managers record court hearings linked to matters — with hearing type (adapted to
Egyptian civil courts), court name, address, courtroom, judge, docket number, opposing counsel,
status, and reminder settings. Hearings appear in the unified calendar and trigger deterministic
reminders.

**Why this priority**: Court date management is time-critical; deterministic reminders are a
constitutional requirement (**[C-IV]**).

**Independent Test**: Create a hearing with a reminder lead time, advance time to the reminder
point, and verify the reminder fires to the responsible lawyer and a `notifications_log` entry
is written; confirm a non-manager cannot delete another lawyer's hearing.

**Acceptance Scenarios**:

1. **Given** a matter, **When** a hearing is created, **Then** it is linked to the matter with
   type, full court details, judge, docket number, opposing counsel, and scheduled date/time.
2. **Given** a hearing with a reminder configured, **When** the lead time is reached, **Then**
   a notification is sent to the assigned lawyer and a `notifications_log` entry is written;
   failures are logged and surfaced, never silently dropped (**[C-IV]**).
3. **Given** a hearing status change (e.g., Adjourned, Completed), **When** saved, **Then**
   status updates and an audit-log entry is written.
4. **Given** a calendar view, **When** a hearing is scheduled, **Then** it appears on the
   correct date with type and matter name.

---

### User Story 7 — Appointment Scheduling with Conflict Detection (Priority: P2)

Lawyers and staff schedule client consultations and internal meetings with status management,
time-slot conflict detection, rescheduling, calendar integration, and notes.

**Why this priority**: Client meeting management is a core daily operational need; integrates
with the unified calendar.

**Independent Test**: Book two appointments for the same lawyer in the same time slot; verify
a conflict warning appears before saving. Reschedule one to an available slot; verify the
calendar and matter view update.

**Acceptance Scenarios**:

1. **Given** an existing appointment in a time slot, **When** a new appointment is booked for
   the same lawyer in the same slot, **Then** a conflict warning is surfaced before saving.
2. **Given** an appointment, **When** rescheduled to an available slot, **Then** it updates
   and the prior slot is released.
3. **Given** an appointment status change (Confirmed, Completed, Cancelled), **When** saved,
   **Then** the calendar and matter view reflect the new status.
4. **Given** a calendar view, **When** an appointment is scheduled, **Then** it appears on the
   correct date alongside hearings.

---

### User Story 8 — Unified Calendar (Priority: P2)

Users view hearings and appointments in a unified monthly/weekly calendar, filter by event
type, navigate by date, and access event details and quick actions from calendar entries.

**Why this priority**: Provides a single time-oriented view of all scheduled obligations;
reduces missed hearings and appointments.

**Independent Test**: Create a hearing and an appointment on different dates; verify both
appear in calendar; filter to "Hearings only" and confirm appointments are hidden; click an
event and verify quick-access details appear.

**Acceptance Scenarios**:

1. **Given** hearings and appointments on a date, **When** the calendar is viewed, **Then**
   all events appear on the correct dates with type labels.
2. **Given** the event type filter, **When** "Hearings" only is selected, **Then** appointments
   are hidden and only hearings display.
3. **Given** a calendar event, **When** clicked, **Then** quick-access details and navigation
   to the full record are shown.

---

### User Story 9 — Client Portal (Priority: P3)

A client authenticates into the firm's portal from the firm's own isolated instance and can
view their matters, access documents explicitly shared with them, track their invoices, view
upcoming consultations, and manage their profile. No cross-firm data exposure is possible.

**Why this priority**: Client self-service value; requires strict per-firm isolation and
content scoping (**[C-I]**, **[C-II]**, **[C-VIII]**).

**Independent Test**: Provision two firm instances. Log in as a client from Firm A; verify
they see zero data from Firm B, zero data from other Firm A clients, and only explicitly
shared documents (no confidential ones). Verify any AI insight shown is approved and
carries the assistive-tool disclaimer.

**Acceptance Scenarios**:

1. **Given** a client account, **When** they log in, **Then** they see only their own matters,
   shared documents, invoices, and consultations — nothing from other clients.
2. **Given** a document not shared with the client, **When** the client navigates to it,
   **Then** access is denied; confidential documents are never visible regardless of sharing.
3. **Given** a client from Firm A, **When** they attempt to reach Firm B's instance, **Then**
   access is denied by the instance boundary (**[C-I]**).
4. **Given** an AI insight surfaced in the portal, **When** displayed, **Then** it has been
   approved by an authorized reviewer, is AI-marked, and carries the assistive-tool disclaimer
   (**[C-II]**, **[C-VIII]**).
5. **Given** a client, **When** they update their profile, **Then** the change is saved and
   audit-logged.

---

### User Story 10 — Analytics & Reporting (Priority: P3)

Managers view a dashboard with real-time KPIs (open matters, upcoming hearings/deadlines,
outstanding invoices, items awaiting AI review), financial reports, operational efficiency
metrics, and a live activity feed. All report data is assembled deterministically from
stored records.

**Why this priority**: Management visibility; deterministic assembly required (**[C-IV]**).

**Independent Test**: With known sample data, view the dashboard and reconcile every KPI to
the underlying stored records; view a financial report and verify totals match invoice/payment
records; confirm a non-manager cannot access analytics.

**Acceptance Scenarios**:

1. **Given** current firm data, **When** the dashboard is viewed, **Then** all KPIs reflect
   actual stored records at the time of display.
2. **Given** a financial report, **When** generated, **Then** revenue and payment totals
   reconcile to audited invoice and payment records.
3. **Given** the activity feed, **When** viewed, **Then** recent creates/updates/deletes appear
   in chronological order sourced from the audit log.
4. **Given** a non-manager user, **When** they attempt to access the Analytics module,
   **Then** access is denied.

---

### User Story 11 — AI Knowledge Search (Priority: P2)

Users search the firm's private document corpus and the shared Egyptian-law corpus using
natural language, receiving grounded results with source links. Legal references are framed
as persuasive support.

**Why this priority**: Direct interactive extension of spec 001's retrieval capability;
high daily utility.

**Acceptance Scenarios**:

1. **Given** a natural-language search query, **When** submitted, **Then** results are returned
   from both private and shared corpora with source links to the exact locations.
2. **Given** a result citing Egyptian law, **When** displayed, **Then** it is framed as
   persuasive support (استشهاد), never as binding precedent or predicted outcome (**[C-IX]**).

---

### User Story 12 — AI Letter Pack Generation (Priority: P2)

A user generates a professional letter pack from a template for a matter or client. AI
pre-fills the template (address, salutation, subject, body, closing) from matter and client
data. The output is `draft_unreviewed` and AI-marked until the assigned lawyer approves it.

**Why this priority**: High-volume correspondence automation; review gate applies to all AI
outputs (**[C-II]**, **[C-VI]**).

**Acceptance Scenarios**:

1. **Given** a matter and a letter template, **When** letter pack generation runs, **Then** a
   draft letter is created in `draft_unreviewed`, pre-filled with matter/client data, and
   visibly AI-marked.
2. **Given** a draft letter, **When** approved by the assigned lawyer or a partner_manager,
   **Then** it becomes exportable and the approval is audit-logged.

---

### User Story 13 — AI Case Timeline Generation (Priority: P2)

A user requests an automatic timeline for a matter. The system extracts dated events (filings,
hearings, decisions, deadlines) from the matter's documents and structured data, assembles
them chronologically, and presents a visual timeline. The timeline output is grounded to its
source data and AI-marked.

**Why this priority**: High orientation value for complex matters with many events; all AI
extraction follows grounding and review gate.

**Acceptance Scenarios**:

1. **Given** a matter with documents and structured events, **When** timeline generation runs,
   **Then** a chronological timeline is produced with each entry grounded to its source
   document/data record.
2. **Given** the timeline output, **When** displayed, **Then** it is AI-marked and each entry
   links to its source for verification.

---

### Edge Cases

- A document checked out by a user who is then deactivated: the check-out is automatically
  released and the event is audit-logged.
- An invoice generated for a matter with no linked client: the system requires a client
  before the invoice status can advance to `pending` or be sent.
- A portal client whose matter is closed: they retain read-only access to shared documents
  and invoices for their closed matter.
- A hearing or appointment with a responsible lawyer who has no registered phone number:
  reminder failure is logged and surfaced rather than silently dropped (**[C-IV]**).
- Concurrent edits to the same invoice: each saved change is independently audit-logged;
  users are warned of a conflict.
- A document version referenced by an approved AI output is subsequently deleted: the
  approved output retains its source reference; the version is archived, not purged.
- An AI contract review is re-run after the source document is updated: a new
  `draft_unreviewed` output is created; the prior approved version is retained as a
  historical record.
- A client attempts to view an AI insight in the portal before it is approved by a lawyer:
  the insight is not surfaced to the client (**[C-II]**).
- An AI letter pack template references a field with no data in the matter: the generation
  produces a draft with clearly marked `[MISSING: field_name]` placeholders, not blank or
  misleading content.

---

## Requirements *(mandatory)*

### Functional Requirements

**AI Document Generation, Review & Correspondence (P1)**

- **FR-101**: Users MUST be able to request AI generation of: contracts, court submissions
  (مذكرات دفاع / مذكرات جلسات), engagement letters, and professional letters; each output MUST
  be born `draft_unreviewed` (**[C-II]**).
- **FR-102**: AI contract review MUST identify clauses against a configurable taxonomy, flag
  missing or unusual clauses, and optionally compare against a firm playbook; all findings
  MUST be grounded to their exact source location (**[C-V]**).
- **FR-103**: Every AI output — generated, reviewed, or extracted — MUST be visibly marked
  "AI-generated — requires review" until approved by the assigned lawyer or a partner_manager
  (**[C-VI]**).
- **FR-104**: AI content citing legal authority MUST be framed as persuasive support
  (استشهاد), never as binding precedent or outcome prediction (**[C-IX]**).
- **FR-105**: Letter pack generation MUST AI-pre-fill a selected template with matter/client
  data; the draft MUST follow the same review gate as all AI outputs (**[C-II]**).
- **FR-106**: Case timeline generation MUST extract dated events from matter documents and
  structured data, grounding each timeline entry to its source (**[C-V]**).
- **FR-107**: The system MUST support configuration of multiple LLM providers — at minimum:
  Gemini, OpenAI, Claude, Mistral, Cohere, and Azure OpenAI — selectable per firm in Settings
  without requiring code changes or redeployment.

**Client Management (P1)**

- **FR-108**: Users MUST be able to create, read, update, and delete client records; each
  new record MUST auto-generate a unique client number (CL-XXXXXX pattern) per instance.
- **FR-109**: Client records MUST support individual and organization types, with multiple
  typed contacts (primary, billing, opposing, witness) per client.
- **FR-110**: The system MUST provide a conflict check that compares a new client or opposing
  party against all active matter parties in the firm's instance and alerts on any match.
- **FR-111**: All client create/update/delete actions MUST produce audit-log entries (**[C-III]**).

**Document Management System (P1)**

- **FR-112**: Users MUST be able to organize matter documents in folder hierarchies and assign
  per-document access levels (public, team, restricted).
- **FR-113**: The DMS MUST provide full version control: each check-in creates a new version
  with a version number and a reference to the root and previous version; all versions MUST
  remain accessible.
- **FR-114**: A checked-out document MUST be locked against simultaneous check-out by any
  other user; the check-out owner, timestamp, and eventual check-in MUST be audit-logged.
- **FR-115**: Documents MAY be marked confidential; confidential documents MUST NOT be
  accessible via the client portal regardless of sharing settings.
- **FR-116**: A template library MUST allow creation, management, and instantiation of
  document templates into matter-linked drafts.
- **FR-117**: Documents MAY be explicitly shared with specific clients, making them visible
  in that client's portal view.

**Case/Matter Extensions (P1)**

- **FR-118**: Matter records MUST support: auto-generated case numbers (CASE-XXXX pattern per
  instance), client link, practice area, court/jurisdiction metadata, opposing counsel,
  docket number, tags, priority level (Low/Medium/High), and matter stage
  (Intake/Active/Litigation/Settlement/Closed).

**Billing & Invoicing (P2)**

- **FR-119**: Users MUST be able to create, read, update, and delete invoices linked to matters
  and clients; each invoice MUST auto-generate a unique number (INV-YYYYMM-XXXXXX pattern).
- **FR-120**: Invoices MUST support service line items with description, quantity, unit price,
  configurable tax, and discount; totals MUST calculate automatically.
- **FR-121**: Invoice statuses MUST follow: Draft → Pending → Partial | Paid | Cancelled,
  with each transition audit-logged (**[C-III]**).
- **FR-122**: Payment recording MUST capture method (cash, bank transfer, cheque, electronic
  wallet, card), amount, date, and reference; partial payments MUST transition status to
  `partial`.
- **FR-123**: A reusable service catalog MUST allow defining items with default descriptions
  and prices for quick invoice line-item entry.

**Hearing Management (P2)**

- **FR-124**: Users MUST be able to create, read, update, and delete hearings linked to
  matters, recording: configurable hearing type, court name, address, courtroom, judge,
  docket number, opposing counsel, scheduled date/time, and status.
- **FR-125**: Default hearing types MUST reflect Egyptian civil court proceedings (e.g., جلسة
  مرافعة, جلسة تسوية ودية, جلسة تحقيق, جلسة إصدار حكم, تأجيل, وساطة); types are
  firm-configurable (**[C-IX]**).
- **FR-126**: Hearing reminders MUST be driven by deterministic scheduled code, not an
  autonomous agent; every reminder attempt (success or failure) MUST be logged (**[C-IV]**).
- **FR-127**: Hearings MUST appear in the unified calendar.

**Appointment Scheduling (P2)**

- **FR-128**: Users MUST be able to create, read, update, and delete appointments with type
  (consultation, follow-up, check-up, emergency), status, assigned lawyer, linked matter/
  client, time slot, duration, and notes.
- **FR-129**: The system MUST detect and surface time-slot conflicts for the same lawyer
  before the appointment is saved.
- **FR-130**: Appointments MUST appear in the unified calendar.

**Unified Calendar (P2)**

- **FR-131**: The calendar MUST display hearings and appointments in a unified month/week view
  with date navigation, event-type filtering, and quick-access details per event.

**Client Portal (P3)**

- **FR-132**: The client portal MUST be served from the firm's own isolated instance; clients
  MUST authenticate through the firm's own auth system; cross-firm access MUST be impossible
  at the instance boundary (**[C-I]**).
- **FR-133**: A portal client MUST see only: matters linked to them, documents explicitly
  shared with them (excluding confidential), invoices issued to them, and consultations
  assigned to them.
- **FR-134**: AI insights surfaced in the portal MUST be approved before display and MUST
  carry the assistive-tool disclaimer (**[C-II]**, **[C-VIII]**).
- **FR-135**: Clients MUST be able to update their own profile; the update MUST be audit-logged.

**Analytics & Reporting (P3)**

- **FR-136**: The dashboard MUST display real-time KPIs: open matters count, hearings and
  deadlines in the next 7 days, invoices awaiting payment, AI outputs awaiting review.
- **FR-137**: Financial reports MUST include revenue by period, outstanding invoices, and
  payment method breakdown; figures MUST derive deterministically from stored invoice/payment
  records (**[C-IV]**).
- **FR-138**: Operational reports MUST include workload by lawyer and matter resolution time
  distribution.
- **FR-139**: An activity feed MUST surface recent system events from the audit log.
- **FR-140**: The Analytics module MUST be restricted to the partner_manager role.

**AI Knowledge Search (P2)**

- **FR-141**: Users MUST be able to query the private and shared corpora via natural language;
  results MUST include source links and persuasive-framing labels for legal references
  (**[C-V]**, **[C-IX]**).

**Task Enhancements (P2 — extends spec 001 FR-042)**

- **FR-142**: Tasks MUST support priority levels (Low, Medium, High) and advanced filtering
  by status, priority, assignee, matter, and due date.

---

### Key Entities (new and extended beyond spec 001)

- **clients** — client_number (CL-XXXXXX), type (individual/organization), name, custom
  identifiers, conflict_check_notes, status. Foreign key from matters.
- **client_contacts** — client_id, contact_type (primary/billing/opposing/witness), name,
  phone, email, address.
- **document_folders** — matter_id, name, parent_folder_id, created_by.
- **document_versions** — document_id, version_number, file_path, root_version_id,
  prev_version_id, uploaded_by, uploaded_at.
- **document_checkouts** — document_id, checked_out_by, checked_out_at, checked_in_at.
- **document_sharing** — document_id, shared_with_client_id, shared_by, shared_at.
- **document_templates** — name, category, content_template, variables_schema, created_by.
- **invoices** — invoice_number (INV-YYYYMM-XXXXXX), matter_id, client_id, status, subtotal,
  tax_rate, tax_amount, discount, total_due, due_date.
- **invoice_items** — invoice_id, description, quantity, unit_price, item_tax, item_discount,
  line_total.
- **payments** — invoice_id, method, amount, payment_date, reference, recorded_by.
- **service_catalog** — name, default_description, default_unit_price.
- **hearings** — matter_id, type, court_name, address, courtroom, judge, docket_number,
  opposing_counsel, scheduled_at, status (Scheduled/Confirmed/In Progress/Completed/
  Cancelled/Adjourned), reminder_days.
- **appointments** — type, matter_id, client_id, assigned_lawyer_id, scheduled_at, duration,
  status (Scheduled/Confirmed/In Progress/Completed/Cancelled), notes, reason.
- **conflict_check_log** — checked_by, checked_at, new_party, matched_matter_id,
  matched_party, result.
- **(extends) cases/matters** — add client_id, case_number (CASE-XXXX), practice_area,
  court, jurisdiction, opposing_counsel, docket_number, tags, priority
  (Low/Medium/High), stage (Intake/Active/Litigation/Settlement/Closed).
- **(extends) users** — add `client` portal-only role; client records link to portal users
  via portal_user_id.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-101**: 100% of AI-generated documents, contract reviews, letter packs, and case
  timelines are born `draft_unreviewed`; 0% reach clients or are exported before an authorized
  lawyer or partner approves them.
- **SC-102**: 100% of invoice, payment, client, and document create/update/delete actions
  produce audit-log entries; 0% of entries can be edited or deleted afterward (**[C-III]**).
- **SC-103**: A client authenticated in the portal sees 0 records belonging to another client
  or another firm.
- **SC-104**: Conflict check completes within 3 seconds for a firm with up to 500 active
  matters and 1,000 client records.
- **SC-105**: 100% of hearing reminders fire from deterministic scheduled code; 0% are
  produced by autonomous agent judgment; 100% of reminder attempts are logged.
- **SC-106**: 100% of AI legal references carry the persuasive-framing disclaimer; 0 outputs
  frame a legal reference as binding or predictive (**[C-IX]**).
- **SC-107**: Dashboard KPIs and financial report totals match underlying stored records at
  all times; no AI-invented figures appear in any report.
- **SC-108**: 100% of checked-in document revisions are preserved as accessible versions;
  no version data is overwritten or lost.
- **SC-109**: Time-slot conflict detection prevents 100% of double-booking attempts without
  an explicit override action.
- **SC-110**: A newly provisioned firm instance can complete the full workflow — client intake
  → matter creation → document upload → AI review → invoice generation → client portal login
  → view shared document — without any cross-firm data exposure.
- **SC-111**: All AI outputs surfaced in the client portal are approved and carry the
  assistive-tool disclaimer; no `draft_unreviewed` content is visible to portal clients.

---

## Assumptions

- **Language**: Arabic is the sole UI language per Option A (Q1) and the locked stack
  ("RTL-first Arabic"). Multi-language support is fully out of scope for this feature.
- **Roles**: Existing roles (partner_manager, lawyer, paralegal, secretary) are kept unchanged
  per Option A (Q2). A new `client` portal-only role is added; no migration of spec 001 is
  required. Admin-level screens in the UI correspond to partner_manager.
- **Hearing types**: Egyptian civil court hearing types are the default (مرافعة, تسوية, حكم,
  تأجيل, etc.); US criminal procedure terms (Arraignment, Sentencing) are excluded as
  inapplicable to the Egyptian civil-law jurisdiction (**[C-IX]**). Types are firm-configurable.
- **Payment methods**: Egyptian-relevant methods (cash, bank transfer, cheque, electronic
  wallet — Vodafone Cash, InstaPay, etc. — and card) replace UPI (Indian payment system not
  used in Egypt). Tax rates are configurable; 14% Egyptian VAT is the default.
- **Client portal isolation**: Each firm's portal is served from that firm's own isolated
  instance at the firm's configured domain/subdomain — consistent with per-firm physical
  isolation (**[C-I]**). No shared portal infrastructure.
- **Auto-generated identifiers**: Case numbers (CASE-XXXX), client numbers (CL-XXXXXX), and
  invoice numbers (INV-YYYYMM-XXXXXX) are generated per-instance; uniqueness is per-firm, not
  globally across firms.
- **Multi-provider LLM**: Each firm configures one active LLM provider at a time in Settings.
  API keys are stored as secrets — logged only as action + who, never as values (**[C-III]**).
- **Public landing page**: A professional informational landing page is included. It makes no
  legal claims and carries the assistive-tool disclaimer (**[C-VIII]**).
- **Responsive design**: The web interface is mobile-responsive and includes a collapsible
  sidebar; this is a UI quality requirement, not a separate native app.
- **Print/PDF**: Print-friendly layouts and PDF export for approved documents and invoices
  are in scope; only approved AI outputs are exportable (**[C-II]**).

## Dependencies

- All spec 001 dependencies remain in force.
- Client portal requires the `client` role and portal auth flow in each firm's instance.
- Analytics and the activity feed require the append-only audit log (spec 001 FR-005).
- Billing reports require the invoices and payments entities from this spec.
- Hearing reminders require the deterministic scheduler from spec 001 (FR-023).
- AI document generation, contract review, and letter pack generation require the LLM
  integration from spec 001.
- Document version control depends on the document pipeline from spec 001 (FR-010–FR-011).

## Out of Scope (this spec)

- Multi-language UI (English/Spanish/French) — confirmed out of scope (Q1 Option A).
- Outcome prediction of any kind (constitutionally prohibited — **[C-IX]**).
- Cross-firm analytics or any shared store of firm/client data.
- Native mobile applications (responsive web only).
- E-filing or court-system integrations.
- Online payment gateway integration (PayMob, Fawry) — future feature.
- Egyptian e-invoicing compliance (Fatoorah) — future compliance feature.
- Client portal subdomain DNS provisioning — covered by infra/provision scripts.
- Shared corpus maintenance and ingestion — covered by spec 001 and shared-corpus tooling.
