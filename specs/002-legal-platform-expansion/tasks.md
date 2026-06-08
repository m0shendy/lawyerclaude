# Tasks: Legal Platform Expansion

**Feature Directory**: `specs/002-legal-platform-expansion`
**Generated**: 2026-06-08
**Plan**: [plan.md](plan.md) · **Spec**: [spec.md](spec.md)
**Total tasks**: 98 across 11 phases
**Constitution**: All tasks subject to inviolable principles I–XII in `.specify/memory/constitution.md`

> **Build order**: Phases follow the plan's A–H sequence (client management → DMS → billing →
> hearings/calendar → AI features → portal → analytics → task enhancements), which respects
> entity dependencies. Foundation tasks (Phase 2) must complete before any user-story phase.
> Spec 001 baseline (auth, audit log, cases, document pipeline, review gate) must be working
> before starting Phase 1.

---

## Phase 1 — Setup

Project-level initialization for the expansion. No user story label.

- [X] T001 Create expansion migration file `supabase/migrations/0017_expansion.sql` with header comment listing all tables to be created (clients, client_contacts, document_folders, document_versions, document_checkouts, document_sharing, document_templates, conflict_check_log, invoices, invoice_items, payments, service_catalog, invoice_sequences, hearings, appointments); file will be populated section-by-section in subsequent tasks

- [X] T002 [P] Add `litellm` to `backend/requirements.txt`; pin to latest stable version

- [X] T003 [P] Create frontend directory structure: `frontend/app/clients/`, `frontend/app/documents/`, `frontend/app/billing/`, `frontend/app/hearings/`, `frontend/app/appointments/`, `frontend/app/calendar/`, `frontend/app/portal/`, `frontend/app/analytics/`; add a placeholder `page.tsx` in each so Next.js route group is registered

- [X] T004 [P] Create empty backend router files: `backend/app/api/clients.py`, `backend/app/api/dms.py`, `backend/app/api/billing.py`, `backend/app/api/hearings.py`, `backend/app/api/appointments.py`, `backend/app/api/calendar.py`, `backend/app/api/portal.py`, `backend/app/api/analytics.py`, `backend/app/api/ai_doc.py`; register all routers in `backend/app/main.py`

- [X] T005 [P] Create LiteLLM wrapper module `backend/app/llm/providers.py` with a skeleton `dispatch(prompt, firm_settings)` function that reads `firm_settings.llm_provider_config` and calls `litellm.completion()`; add error handling for invalid provider and missing API key

---

## Phase 2 — Foundation

Shared infrastructure that multiple user-story phases depend on. Must complete before Phase 3.

- [X] T006 Add `firm_settings` extension to `supabase/migrations/0017_expansion.sql`: add columns `llm_provider_config JSONB DEFAULT '{"provider":"gemini","model":"models/gemini-2.0-flash","api_key":""}'::jsonb`, `feature_client_portal BOOLEAN DEFAULT true`, `checkout_timeout_hours INTEGER DEFAULT 24`

- [X] T007 [P] Add Postgres sequences and case_number to `supabase/migrations/0017_expansion.sql`: `CREATE SEQUENCE cases_number_seq START 1;` then `ALTER TABLE cases ADD COLUMN IF NOT EXISTS case_number TEXT UNIQUE GENERATED ALWAYS AS ('CASE-' || lpad(nextval('cases_number_seq')::text, 4, '0')) STORED`; also add columns `client_id UUID REFERENCES clients(id)`, `practice_area TEXT`, `court TEXT`, `jurisdiction TEXT`, `opposing_counsel TEXT`, `docket_number TEXT`, `tags TEXT[]`, `priority TEXT DEFAULT 'medium' CHECK (priority IN ('low','medium','high'))`, `stage TEXT DEFAULT 'intake' CHECK (stage IN ('intake','active','litigation','settlement','closed'))`

- [ ] T008 [P] Add `invoice_sequences` helper table and `next_invoice_counter()` function to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE TABLE invoice_sequences (year_month CHAR(6) PRIMARY KEY, last_counter INTEGER DEFAULT 0);
  CREATE OR REPLACE FUNCTION next_invoice_counter(ts TIMESTAMPTZ) RETURNS INTEGER AS $$
    INSERT INTO invoice_sequences (year_month, last_counter) VALUES (to_char(ts,'YYYYMM'), 1)
    ON CONFLICT (year_month) DO UPDATE SET last_counter = invoice_sequences.last_counter + 1
    RETURNING last_counter; $$ LANGUAGE SQL;
  ```

- [X] T009 Extend audit trigger function in `supabase/migrations/0017_expansion.sql` to register triggers on all 14 new tables created in this expansion: after all `CREATE TABLE` statements, add `CREATE TRIGGER audit_<table> AFTER INSERT OR UPDATE OR DELETE ON <table> FOR EACH ROW EXECUTE FUNCTION audit_log_trigger()` for each of: clients, client_contacts, document_folders, document_versions, document_checkouts, document_sharing, document_templates, invoices, invoice_items, payments, service_catalog, hearings, appointments, conflict_check_log

- [X] T010 [P] Extend `ai_outputs.type` enum in `supabase/migrations/0017_expansion.sql`: `ALTER TYPE ai_output_type ADD VALUE IF NOT EXISTS 'doc_draft'; ALTER TYPE ai_output_type ADD VALUE IF NOT EXISTS 'letter_pack'; ALTER TYPE ai_output_type ADD VALUE IF NOT EXISTS 'case_timeline';`; also add column `template_id UUID REFERENCES document_templates(id)` to `ai_outputs`

- [ ] T011 [P] Extend `users` table in `supabase/migrations/0017_expansion.sql`: add `client` to the role enum `ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'client';`; add column `client_id UUID REFERENCES clients(id) NULL` (only populated when role = 'client')

- [ ] T012 Create `backend/app/models/expansion.py` with Pydantic base models shared across the expansion: `PaginationParams`, `AuditedBase` (with `created_by`, `created_at`), and `ConstitutionNote` docstring reminder that every AI output must be `draft_unreviewed` **[C-II]**

---

## Phase 3 — US3: Client Management (P1)

**Story goal**: Staff and lawyers create/manage client records with auto-numbering, typed contacts, and conflict-check alerting.
**Independent test**: Create an individual client (CL-000001 auto-generated), add an opposing contact, run conflict check against an existing matter — alert fires; all actions are audit-logged.

- [ ] T013 [US3] Add `clients` and `client_contacts` DDL to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE SEQUENCE clients_number_seq START 1;
  CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_number TEXT UNIQUE GENERATED ALWAYS AS ('CL-' || lpad(nextval('clients_number_seq')::text,6,'0')) STORED,
    type TEXT NOT NULL CHECK (type IN ('individual','organization')),
    name TEXT NOT NULL,
    conflict_check_notes TEXT,
    custom_identifier TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
  );
  CREATE TABLE client_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('primary','billing','opposing','witness')),
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    address TEXT
  );
  ```

- [ ] T014 [US3] Add tsvector full-text index for conflict check to `supabase/migrations/0017_expansion.sql`:
  ```sql
  ALTER TABLE clients ADD COLUMN name_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', name)) STORED;
  ALTER TABLE client_contacts ADD COLUMN name_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', name)) STORED;
  ALTER TABLE cases ADD COLUMN opposing_counsel_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(opposing_counsel,''))) STORED;
  CREATE INDEX idx_clients_name_tsv ON clients USING GIN (name_tsv);
  CREATE INDEX idx_contacts_name_tsv ON client_contacts USING GIN (name_tsv);
  CREATE INDEX idx_cases_opposing_tsv ON cases USING GIN (opposing_counsel_tsv);
  ```

- [ ] T015 [US3] Add `conflict_check_log` DDL to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE TABLE conflict_check_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checked_by UUID REFERENCES users(id),
    checked_at TIMESTAMPTZ DEFAULT now(),
    new_party_name TEXT NOT NULL,
    matched_matter_id UUID REFERENCES cases(id),
    matched_party_name TEXT,
    result TEXT NOT NULL CHECK (result IN ('clear','conflict_found'))
  );
  ```

- [ ] T016 [P] [US3] Add RLS policies for `clients`, `client_contacts`, `conflict_check_log` to `supabase/migrations/0017_expansion.sql`: non-client roles get full CRUD on own-instance rows; `client` role gets SELECT on own `clients` row only (WHERE id = current_setting('app.client_id')::uuid)

- [X] T017 [P] [US3] Implement `backend/app/models/clients.py` with Pydantic schemas: `ClientCreate`, `ClientUpdate`, `ClientResponse` (includes `client_number`), `ContactCreate`, `ContactResponse`, `ConflictCheckRequest` (`party_name: str`), `ConflictCheckResponse` (`result`, `conflicts: list`)

- [X] T018 [US3] Implement `backend/app/api/clients.py`: `GET/POST /clients`, `GET/PATCH/DELETE /clients/{id}`, `GET/POST /clients/{id}/contacts`, `PATCH/DELETE /clients/{id}/contacts/{cid}`, `POST /clients/conflict-check` — conflict check queries tsvector index across clients, client_contacts, and cases.opposing_counsel for active matters; inserts into conflict_check_log; returns matches

- [X] T019 [P] [US3] Extend `backend/app/api/cases.py` to accept and return the new matter fields (`client_id`, `practice_area`, `court`, `jurisdiction`, `opposing_counsel`, `docket_number`, `tags`, `priority`, `stage`, `case_number`); update Pydantic models in `backend/app/models/cases.py`

- [X] T020 [P] [US3] Create `frontend/app/clients/page.tsx` — client list with search, type/status filters, and "New Client" button leading to create form

- [X] T021 [P] [US3] Create `frontend/app/clients/[id]/page.tsx` — client detail showing profile, typed contacts list, linked matters, and linked invoices (stubs for billing phase)

- [X] T022 [US3] Create `frontend/components/ConflictCheckPanel.tsx` — inline conflict check widget that fires `POST /clients/conflict-check` on opposing-party name entry and displays any matches with conflict notes; reused in client create/edit form

---

## Phase 4 — US4: Document Management System (P1)

**Story goal**: Organize documents in folders with full version history, exclusive check-in/out, access controls, confidentiality flags, template library, and client sharing.
**Independent test**: Check out a document (second user gets 409), check in a new version (prior version preserved), mark a document confidential (portal access denied), share a non-confidential document with a client (visible in portal).

- [X] T023 [US4] Add DMS DDL to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE TABLE document_folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matter_id UUID NOT NULL REFERENCES cases(id),
    name TEXT NOT NULL,
    parent_folder_id UUID REFERENCES document_folders(id),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
  );
  CREATE TABLE document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),
    version_number INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    root_version_id UUID REFERENCES document_versions(id),
    prev_version_id UUID REFERENCES document_versions(id),
    folder_id UUID REFERENCES document_folders(id),
    access_level TEXT DEFAULT 'team' CHECK (access_level IN ('public','team','restricted')),
    is_confidential BOOLEAN DEFAULT false,
    uploaded_by UUID REFERENCES users(id),
    uploaded_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (document_id, version_number)
  );
  CREATE TABLE document_checkouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL UNIQUE REFERENCES documents(id),
    checked_out_by UUID NOT NULL REFERENCES users(id),
    checked_out_at TIMESTAMPTZ DEFAULT now()
  );
  CREATE TABLE document_sharing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),
    shared_with_client_id UUID NOT NULL REFERENCES clients(id),
    shared_by UUID REFERENCES users(id),
    shared_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (document_id, shared_with_client_id)
  );
  CREATE TABLE document_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    category TEXT CHECK (category IN ('contract','submission','engagement_letter','letter','other')),
    content_template TEXT NOT NULL,
    variables_schema JSONB DEFAULT '[]'::jsonb,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
  );
  ```

- [X] T024 [US4] Add DB constraint preventing sharing of confidential documents to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE OR REPLACE FUNCTION check_no_confidential_sharing() RETURNS TRIGGER AS $$
  BEGIN
    IF EXISTS (SELECT 1 FROM document_versions WHERE document_id = NEW.document_id AND is_confidential = true ORDER BY version_number DESC LIMIT 1) THEN
      RAISE EXCEPTION 'Cannot share a confidential document';
    END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;
  CREATE TRIGGER no_confidential_sharing BEFORE INSERT ON document_sharing
    FOR EACH ROW EXECUTE FUNCTION check_no_confidential_sharing();
  ```

- [X] T025 [P] [US4] Add RLS policies for DMS tables to `supabase/migrations/0017_expansion.sql`: non-client roles CRUD on own-instance rows; `client` role — `document_versions`: SELECT only on non-confidential documents with a `document_sharing` entry for their client_id; `document_sharing`, `document_checkouts`, `document_templates`, `document_folders`: denied for `client` role

- [X] T026 [P] [US4] Implement `backend/app/models/dms.py` with Pydantic schemas: `FolderCreate`, `FolderResponse`, `VersionResponse`, `CheckoutResponse`, `SharingCreate`, `TemplateCreate`, `TemplateUpdate`, `TemplateResponse`, `GenerateFromTemplateRequest` (`matter_id`, `template_id`, optional `context`)

- [X] T027 [US4] Implement folder and version endpoints in `backend/app/api/dms.py`:
  - `GET /folders?matter_id=` — folder tree
  - `POST /folders`, `PATCH /folders/{id}`, `DELETE /folders/{id}`
  - `GET /documents/{id}/versions`, `GET /documents/{id}/versions/{vid}`

- [X] T028 [US4] Implement check-out/check-in endpoints in `backend/app/api/dms.py`:
  - `POST /documents/{id}/checkout` — INSERT into document_checkouts; return 409 if unique constraint violation (already checked out)
  - `DELETE /documents/{id}/checkout` — DELETE checkout without new version
  - `POST /documents/{id}/checkin` — multipart upload: store file in Supabase Storage at `docs/{doc_id}/v{N}/{filename}`; INSERT document_versions with version_number = max(current)+1, prev_version_id = current version; DELETE checkout row; audit-log both check-in and checkout-release events **[C-III]**

- [X] T029 [P] [US4] Implement document sharing and access endpoints in `backend/app/api/dms.py`:
  - `PATCH /documents/{id}/access` — update access_level and is_confidential on latest document_versions row
  - `POST /documents/{id}/share` / `DELETE /documents/{id}/share/{client_id}` — insert/delete document_sharing; API rejects sharing if is_confidential = true

- [ ] T030 [P] [US4] Implement template CRUD + generate in `backend/app/api/dms.py`:
  - `GET/POST/PATCH/DELETE /templates`
  - `POST /templates/{id}/generate` — pass 1: Mustache variable substitution from matter/client data; pass 2: LiteLLM dispatch for `{{AI: …}}` blocks; INSERT ai_outputs row (type=`doc_draft`, review_state=`draft_unreviewed`) **[C-II]**; mark missing variables as `[MISSING: var_name]`

- [ ] T031 [US4] Extend spec 001 deterministic scheduler in `backend/app/scheduler/` to add a stale-checkout release job: query `document_checkouts WHERE checked_out_at < now() - (firm_settings.checkout_timeout_hours * interval '1 hour')`, DELETE rows, INSERT audit_log entries with action=`doc_checkout_expired` **[C-IV]**

- [ ] T032 [P] [US4] Create `frontend/app/documents/FolderTree.tsx` — recursive folder tree component with collapse/expand, drag-to-move (optional), and "New Folder" inline action

- [ ] T033 [P] [US4] Create `frontend/app/documents/VersionHistory.tsx` — version chain list with version number, upload date/user, download button per version; shows "Checked out by [name]" badge when locked

- [ ] T034 [P] [US4] Create `frontend/app/documents/CheckoutControls.tsx` — check-out button (disabled if locked by another user, shows locker name), check-in button with file upload; wires to `POST/DELETE /documents/{id}/checkout` and `POST /documents/{id}/checkin`

- [ ] T035 [US4] Create `frontend/app/documents/templates/page.tsx` — template library list with category filter; `frontend/app/documents/templates/[id]/page.tsx` — template editor with variable schema builder and "Generate Draft" button; calls `POST /templates/{id}/generate`

---

## Phase 5 — US5: Billing & Invoicing (P2)

**Story goal**: Lawyers generate invoices with auto-numbers, line items, Egyptian payment methods, and full lifecycle tracking. Clients view their invoices in the portal.
**Independent test**: Create INV-202606-000001, add line items with 14% tax, issue invoice (→ pending), record partial bank transfer payment (→ partial), record remainder (→ paid); all state transitions are audit-logged.

- [X] T036 [US5] Add billing DDL to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE TABLE service_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    default_description TEXT,
    default_unit_price NUMERIC(12,2),
    created_by UUID REFERENCES users(id)
  );
  CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number TEXT UNIQUE GENERATED ALWAYS AS
      ('INV-' || to_char(created_at,'YYYYMM') || '-' || lpad(next_invoice_counter(created_at)::text,6,'0')) STORED,
    matter_id UUID REFERENCES cases(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft','pending','partial','paid','cancelled')),
    subtotal NUMERIC(12,2) DEFAULT 0,
    tax_rate NUMERIC(5,2) DEFAULT 14.00,
    tax_amount NUMERIC(12,2) GENERATED ALWAYS AS (subtotal * tax_rate / 100) STORED,
    discount NUMERIC(12,2) DEFAULT 0,
    total_due NUMERIC(12,2) GENERATED ALWAYS AS (subtotal + (subtotal * tax_rate / 100) - discount) STORED,
    due_date DATE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
  );
  CREATE TABLE invoice_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    quantity NUMERIC(10,3) DEFAULT 1,
    unit_price NUMERIC(12,2) NOT NULL,
    item_tax_rate NUMERIC(5,2),
    item_discount NUMERIC(12,2) DEFAULT 0,
    line_total NUMERIC(12,2) GENERATED ALWAYS AS (quantity * unit_price - COALESCE(item_discount,0)) STORED
  );
  CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES invoices(id),
    method TEXT NOT NULL CHECK (method IN ('cash','bank_transfer','cheque','electronic_wallet','card')),
    amount NUMERIC(12,2) NOT NULL,
    payment_date DATE NOT NULL,
    reference TEXT,
    recorded_by UUID REFERENCES users(id),
    recorded_at TIMESTAMPTZ DEFAULT now()
  );
  ```

- [X] T037 [US5] Add invoice status update trigger to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE OR REPLACE FUNCTION update_invoice_status() RETURNS TRIGGER AS $$
  DECLARE paid_sum NUMERIC;
  BEGIN
    SELECT COALESCE(SUM(amount),0) INTO paid_sum FROM payments WHERE invoice_id = NEW.invoice_id;
    IF paid_sum >= (SELECT total_due FROM invoices WHERE id = NEW.invoice_id) THEN
      UPDATE invoices SET status = 'paid' WHERE id = NEW.invoice_id;
    ELSIF paid_sum > 0 THEN
      UPDATE invoices SET status = 'partial' WHERE id = NEW.invoice_id;
    END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;
  CREATE TRIGGER payment_updates_invoice AFTER INSERT ON payments
    FOR EACH ROW EXECUTE FUNCTION update_invoice_status();
  ```

- [ ] T038 [P] [US5] Add RLS policies for billing tables to `supabase/migrations/0017_expansion.sql`: `partner_manager`, `lawyer` CRUD; `paralegal`, `secretary` SELECT only on invoices/items/payments; `client` role SELECT on invoices and payments WHERE client_id = auth.client_id (portal use)

- [X] T039 [P] [US5] Implement `backend/app/models/billing.py`: `InvoiceCreate`, `InvoiceUpdate`, `InvoiceResponse` (includes `invoice_number`, computed totals), `InvoiceItemCreate`, `PaymentCreate`, `PaymentResponse`, `ServiceCatalogItem`

- [X] T040 [US5] Implement `backend/app/api/billing.py` invoice endpoints: `GET/POST /invoices`, `GET/PATCH /invoices/{id}`, `POST /invoices/{id}/issue` (draft→pending), `POST /invoices/{id}/cancel`; validate that edit is only allowed on `draft` invoices (return 422 otherwise); audit-log all transitions **[C-III]**

- [X] T041 [P] [US5] Implement invoice items + service catalog endpoints in `backend/app/api/billing.py`: `GET/POST /invoices/{id}/items`, `PATCH/DELETE /invoices/{id}/items/{iid}`; `GET/POST/PATCH/DELETE /service-catalog`; after item changes, recalculate invoice subtotal

- [X] T042 [P] [US5] Implement payment recording in `backend/app/api/billing.py`: `POST /invoices/{id}/payments` — validate amount > 0 and invoice status not `paid`/`cancelled`; INSERT payment; the DB trigger updates invoice status automatically; audit-log action=`payment_recorded` **[C-III]**

- [X] T043 [P] [US5] Create `frontend/app/billing/page.tsx` — invoice list with status badges, client/matter filters, totals summary bar; "New Invoice" button (partner_manager and lawyer only)

- [X] T044 [US5] Create `frontend/app/billing/[id]/page.tsx` — invoice detail: header info, line items table with calculated totals, payment history, status timeline; `frontend/app/billing/new/page.tsx` — invoice create/edit form with service-catalog lookup for line items, tax/discount inputs, auto-display of calculated total

---

## Phase 6 — US6 + US7 + US8: Hearings, Appointments & Calendar (P2)

**Story goal**: Record court hearings (Egyptian civil types) and client appointments; detect booking conflicts; view all scheduled events in a unified month/week calendar; hearing reminders fire via deterministic scheduler.
**Independent test**: Create hearing 3 days out with reminder=3; scheduler fires notification and logs it; attempt to double-book same lawyer (409); both events appear in calendar view with correct type filter.

- [X] T045 [US6] [US7] [US8] Add hearings and appointments DDL to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE TABLE hearings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matter_id UUID NOT NULL REFERENCES cases(id),
    type TEXT NOT NULL DEFAULT 'murafa_a',
    court_name TEXT,
    court_address TEXT,
    courtroom TEXT,
    judge TEXT,
    docket_number TEXT,
    opposing_counsel TEXT,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'scheduled' CHECK (status IN ('scheduled','confirmed','in_progress','completed','cancelled','adjourned')),
    reminder_days INTEGER DEFAULT 3,
    assigned_lawyer_id UUID REFERENCES users(id),
    notes TEXT,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
  );
  CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL CHECK (type IN ('consultation','follow_up','checkup','emergency')),
    matter_id UUID REFERENCES cases(id),
    client_id UUID REFERENCES clients(id),
    assigned_lawyer_id UUID NOT NULL REFERENCES users(id),
    scheduled_at TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER DEFAULT 60,
    status TEXT DEFAULT 'scheduled' CHECK (status IN ('scheduled','confirmed','in_progress','completed','cancelled')),
    reason TEXT,
    notes TEXT,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
  );
  ```

- [X] T046 [US8] Add `calendar_events` view to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE VIEW calendar_events AS
    SELECT id, 'hearing' AS event_type, type AS title, scheduled_at,
           scheduled_at + INTERVAL '2 hours' AS end_at,
           matter_id, assigned_lawyer_id, status FROM hearings
    UNION ALL
    SELECT id, 'appointment' AS event_type, type AS title, scheduled_at,
           scheduled_at + (duration_minutes * INTERVAL '1 minute') AS end_at,
           matter_id, assigned_lawyer_id, status FROM appointments;
  ```

- [X] T047 [P] [US6] [US7] Add RLS for hearings and appointments to `supabase/migrations/0017_expansion.sql`: non-client roles CRUD; `client` role: SELECT on appointments WHERE client_id = auth.client_id only (no access to hearings)

- [X] T048 [P] [US6] [US7] [US8] Implement `backend/app/models/hearings.py`: `HearingCreate`, `HearingUpdate`, `HearingResponse`, `AppointmentCreate`, `AppointmentUpdate`, `AppointmentResponse`, `CalendarEventResponse`

- [X] T049 [US6] Implement `backend/app/api/hearings.py`: `GET/POST /hearings`, `GET/PATCH/DELETE /hearings/{id}`, `POST /hearings/{id}/confirm` (sets status=confirmed, audit-logged); include `?matter_id=`, `?status=`, `?from=`, `?to=` query params

- [X] T050 [US7] Implement `backend/app/api/appointments.py`: `GET/POST /appointments`, `GET/PATCH/DELETE /appointments/{id}`; on POST/PATCH, run conflict detection: `SELECT 1 FROM appointments WHERE assigned_lawyer_id=? AND status NOT IN ('cancelled','completed') AND tstzrange(scheduled_at, scheduled_at + duration_minutes*'1 minute'::interval) && tstzrange($new_start, $new_end)` — return 409 with `error: appointment_time_conflict` if match found

- [X] T051 [P] [US8] Implement `backend/app/api/calendar.py`: `GET /calendar` — query `calendar_events` view with `?from=`, `?to=`, `?type=all|hearing|appointment`, `?lawyer_id=`; return unified list sorted by `scheduled_at`

- [X] T052 [US6] Extend spec 001 deterministic scheduler in `backend/app/scheduler/` with hearing reminder job: each morning (Africa/Cairo 08:00) query `hearings WHERE status IN ('scheduled','confirmed') AND scheduled_at::date = CURRENT_DATE + reminder_days`; send WAHA notification to assigned_lawyer; if `scheduled_at::date = CURRENT_DATE + 1 AND status = 'scheduled'` (not yet confirmed), also notify a `partner_manager`; INSERT `notifications_log` entry; log failures, never silently drop **[C-IV]**

- [X] T053 [P] [US6] Create `frontend/app/hearings/page.tsx` — hearing list with matter/status/date filters; `frontend/app/hearings/[id]/page.tsx` — hearing detail with court info; `frontend/app/hearings/new/page.tsx` — create/edit form with Egyptian hearing type dropdown (مرافعة, تسوية ودية, تحقيق, إصدار حكم, تأجيل, وساطة, تحكيم, other)

- [ ] T054 [P] [US7] Create `frontend/app/appointments/page.tsx` — appointment list with lawyer/type/status/date filters; `frontend/app/appointments/[id]/page.tsx` — appointment detail; `frontend/app/appointments/new/page.tsx` — create/edit form; inline conflict warning component (shows 409 error inline, requires user to choose a different time before saving)

- [X] T055 [US8] Create `frontend/app/calendar/page.tsx` — unified calendar: month/week toggle, date navigation (prev/next), event-type filter chips (All / Hearings / Appointments); each event rendered as a colored chip with type label; click → quick-detail popover with matter link and status; popover has "Edit" link to full record

---

## Phase 7 — US1 + US2 + US11 + US12 + US13: AI Document Features (P1/P2)

**Story goal**: Lawyers generate AI drafts (contracts, submissions, letters, letter packs, case timelines), trigger AI contract review with clause findings, and search knowledge base — all outputs born `draft_unreviewed`, grounded, AI-marked, and gated. Multi-provider LLM is switchable from Settings.
**Independent test**: Generate a contract draft via Gemini provider; verify `draft_unreviewed`, AI marked, export blocked; approve; export succeeds; switch provider to OpenAI in Settings; generate again — no code change needed.

- [ ] T056 [US1] [US2] [US12] [US13] Complete `backend/app/llm/providers.py` — full implementation of `dispatch(prompt: str, source_chunks: list, firm_settings)`: reads `llm_provider_config`, calls `litellm.completion(model="<provider>/<model>", api_key=..., messages=[...])`, extracts content and parses source citations from the response; raises `LLMProviderError` on auth failure or timeout

- [ ] T057 [P] [US1] [US2] Implement LLM provider settings endpoints in `backend/app/api/billing.py` (or a new `settings.py`): `PATCH /settings/llm-provider` — update `firm_settings.llm_provider_config`; store api_key encrypted; audit-log action=`llm_provider_updated` with who/when — NEVER log the key value **[C-III]**; `POST /settings/llm-provider/test` — dispatch a simple test prompt; return provider name and latency

- [ ] T058 [US1] Implement AI document draft endpoint in `backend/app/api/ai_doc.py`: `POST /ai/draft-document` — accepts `{ matter_id, doc_type, template_id?, context? }`; if template_id provided: run Mustache substitution first; retrieve relevant chunks from both private and shared corpora (Component A); call LiteLLM with matter context + chunks (Component B); INSERT `ai_outputs` row with type=`doc_draft`, `review_state='draft_unreviewed'`, `source_links=[{chunk_id, page_ref}]`; return output id **[C-II][C-V]**

- [ ] T059 [US2] Implement AI contract review endpoint in `backend/app/api/ai_doc.py`: `POST /ai/contract-review` — accepts `{ document_id, playbook_id? }`; retrieve document chunks; call LiteLLM with clause-taxonomy prompt (identify clauses, flag missing/unusual relative to playbook); INSERT multiple `ai_outputs` rows (type=`clause_flag`/`analysis`), each grounded to source chunk **[C-II][C-V]**; contract findings MUST describe existing content only, never predict outcomes **[C-VIII][C-IX]**

- [ ] T060 [P] [US12] Implement AI letter pack endpoint in `backend/app/api/ai_doc.py`: `POST /ai/letter-pack` — accepts `{ matter_id, template_id, context? }`; Mustache substitution for deterministic fields; LiteLLM for `{{AI: …}}` blocks; INSERT `ai_outputs` (type=`letter_pack`, `draft_unreviewed`); mark missing variables as `[MISSING: var_name]` — never leave them blank **[C-II]**

- [ ] T061 [P] [US13] Implement AI case timeline endpoint in `backend/app/api/ai_doc.py`: `POST /ai/case-timeline` — accepts `{ matter_id }`; retrieve all document chunks + structured events (hearings, deadlines, tasks) for the matter; call LiteLLM to extract and chronologically order dated events; INSERT `ai_outputs` (type=`case_timeline`, `draft_unreviewed`); each timeline entry in `source_links` must cite its source chunk or structured record id **[C-V]**

- [ ] T062 [US11] Implement AI knowledge search endpoint in `backend/app/api/ai_doc.py`: `GET /ai/knowledge-search?q=&corpus=all|private|shared` — embed query (Component A), pgvector search private and/or shared corpus, return top-k results with source links; for results from the shared Egyptian-law corpus, add `"type": "persuasive_reference"` and `"frame": "istishhad"` to the response payload **[C-IX]**; no `ai_outputs` row created (search is read-only)

- [ ] T063 [US1] [US2] Implement `POST /ai/outputs/{id}/approve` in `backend/app/api/ai_doc.py`: verify caller is the assigned lawyer on the matter or a partner_manager (paralegals and secretaries → 403); set `review_state='approved'`, `approved_by`, `approved_at`, `approved_version`; audit-log as high-value event **[C-II][C-III]**; after approval, enable export/download of the output

- [ ] T064 [P] [US1] Create `frontend/app/ai/draft/page.tsx` — AI document draft generator: matter selector, doc_type dropdown (contract, submission, engagement_letter, letter), optional template selector; "Generate Draft" button; result shown in `<AiMarkedOutput/>` component with source link panel; Approve button (lawyer/PM only); export button (disabled until approved)

- [ ] T065 [P] [US2] Create `frontend/app/ai/contract-review/page.tsx` — contract review panel: document selector, optional playbook selector; "Run Review" button; findings list showing each clause finding with source location chip; each item in `<AiMarkedOutput/>` wrapper with individual approve action; risk flags display "existing content only" disclaimer **[C-VIII]**

- [ ] T066 [P] [US12] Create `frontend/app/ai/letter-pack/page.tsx` — letter pack generator: matter selector, template selector with preview of variables; "Generate" button; output in `<AiMarkedOutput/>` with `[MISSING: …]` placeholders highlighted in orange

- [ ] T067 [P] [US13] Create `frontend/app/ai/case-timeline/page.tsx` — case timeline view: "Generate Timeline" button per matter; resulting timeline rendered chronologically with event date, description, source chip; AI-marked header; approve button

- [ ] T068 [P] [US11] Create `frontend/app/ai/knowledge-search/page.tsx` — knowledge search: natural language input, corpus filter (All / Private / Shared Law); results list with source location chip; results from shared corpus display Arabic label "مرجع استشهادي — غير ملزم" (persuasive reference — not binding) **[C-IX]**

- [ ] T069 [US1] [US2] Create `frontend/app/settings/llm-provider/page.tsx` — LLM provider settings panel (partner_manager only): provider dropdown, model input, API key masked input; "Test Connection" button shows latency; save button; settings page confirms key is stored securely and never shown again after save

---

## Phase 8 — US9: Client Portal (P3)

**Story goal**: A client user authenticates through the firm's own instance and views only their own matters, shared non-confidential documents, invoices, and consultations. AI insights shown only post-approval with assistive-tool disclaimer.
**Independent test**: Create client user, log in to portal, verify: own matters only, zero other-client data, confidential docs denied, draft_unreviewed AI insights hidden, invoice totals correct, profile edit audit-logged.

- [ ] T070 [US9] Finalize `client` role in `supabase/migrations/0017_expansion.sql` — ensure all portal-relevant RLS policies are applied and `client` role JWT claim is parsed via `current_setting('request.jwt.claims')::json->>'role'`; add `clients.portal_user_id UUID REFERENCES auth.users(id)` column; add index `CREATE INDEX idx_clients_portal_user ON clients(portal_user_id)`

- [ ] T071 [P] [US9] Add portal-specific RLS policies to `supabase/migrations/0017_expansion.sql` for cases, document_versions, document_sharing, invoices, payments, appointments: each `client` role policy uses `client_id = (SELECT id FROM clients WHERE portal_user_id = auth.uid())` as the row filter; ensure `draft_unreviewed` ai_outputs are excluded from portal policy on ai_outputs

- [X] T072 [P] [US9] Implement `backend/app/api/portal.py` with all portal endpoints (all require `role=client` claim):
  - `GET /portal/matters`, `GET /portal/matters/{id}`
  - `GET /portal/documents`, `GET /portal/documents/{id}/download` (pre-signed Storage URL)
  - `GET /portal/invoices`, `GET /portal/invoices/{id}`
  - `GET /portal/appointments`
  - `GET /portal/ai-insights` — SELECT from ai_outputs WHERE review_state='approved' AND matter linked to client
  - `GET/PATCH /portal/profile` — PATCH audit-logged **[C-III]**

- [ ] T073 [US9] Create Next.js portal route group `frontend/app/portal/layout.tsx` with role guard: if JWT claim `role !== 'client'` → redirect to `/login`; portal layout uses same RTL Arabic base but without the main app sidebar; render assistive-tool disclaimer in footer: "هذا النظام أداة مساعدة للمحامين. المسؤولية المهنية تقع على عاتق المحامي." **[C-VIII]**

- [ ] T074 [P] [US9] Create `frontend/app/portal/page.tsx` (dashboard): KPI cards (open matters, shared documents, pending invoices, upcoming consultations, approved AI insights); activity summary

- [ ] T075 [P] [US9] Create `frontend/app/portal/matters/page.tsx` and `frontend/app/portal/matters/[id]/page.tsx` — read-only matter views; no internal notes, opposing counsel, or audit log fields exposed

- [X] T076 [P] [US9] Create `frontend/app/portal/documents/page.tsx` — folder tree of shared non-confidential documents with download button; `frontend/app/portal/invoices/page.tsx` and `[id]/page.tsx` — invoice list and detail (status, items, payments); `frontend/app/portal/appointments/page.tsx` — upcoming consultations list

- [ ] T077 [P] [US9] Create `frontend/app/portal/insights/page.tsx` — approved AI insights list; each item rendered with `<AiMarkedOutput/>` showing the AI-marked banner and assistive-tool disclaimer even post-approval **[C-VI][C-VIII]**

- [ ] T078 [US9] Create `frontend/app/portal/profile/page.tsx` — client profile view with editable contact fields; calls `PATCH /portal/profile`; shows success confirmation after save

---

## Phase 9 — US10: Analytics & Reporting (P3)

**Story goal**: Admins (partner_manager) view real-time KPI dashboard, financial and operational reports, and activity feed — all assembled deterministically from stored data.
**Independent test**: Create sample data across matters/hearings/invoices/ai_outputs; view dashboard — KPIs match counts; financial report totals match invoice/payment records; non-PM gets 403.

- [ ] T079 [US10] Add `dashboard_kpis` materialized view to `supabase/migrations/0017_expansion.sql`:
  ```sql
  CREATE MATERIALIZED VIEW dashboard_kpis AS SELECT
    (SELECT count(*) FROM cases WHERE stage != 'closed') AS open_matters,
    (SELECT count(*) FROM hearings WHERE status IN ('scheduled','confirmed')
       AND scheduled_at BETWEEN now() AND now() + INTERVAL '7 days') AS upcoming_hearings,
    (SELECT count(*) FROM deadlines WHERE confirmed=true
       AND due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7) AS upcoming_deadlines,
    (SELECT count(*) FROM invoices WHERE status IN ('pending','partial')) AS pending_invoices,
    (SELECT count(*) FROM ai_outputs WHERE review_state='draft_unreviewed') AS pending_review;
  ```

- [ ] T080 [US10] Add materialized-view refresh trigger to `supabase/migrations/0017_expansion.sql`: create a `refresh_dashboard_kpis()` function that calls `REFRESH MATERIALIZED VIEW CONCURRENTLY dashboard_kpis`; create AFTER INSERT/UPDATE triggers on `cases`, `hearings`, `deadlines`, `invoices`, `ai_outputs` that call this function; note: `CONCURRENTLY` requires a unique index on the view — add `CREATE UNIQUE INDEX ON dashboard_kpis ((1))`

- [X] T081 [P] [US10] Implement `backend/app/models/analytics.py`: `DashboardKPIs`, `FinancialReportRow`, `WorkloadRow`, `ActivityFeedItem`

- [X] T082 [US10] Implement `backend/app/api/analytics.py` with partner_manager-only guard (return 403 for other roles):
  - `GET /analytics/dashboard` — reads `dashboard_kpis` materialized view
  - `GET /analytics/financial?from=&to=` — aggregate invoices + payments: revenue by period, outstanding total, payment method breakdown
  - `GET /analytics/operational` — aggregate cases by lawyer (case_assignments), calculate mean resolution time for closed cases
  - `GET /analytics/activity-feed?limit=&offset=` — SELECT from audit_log ORDER BY created_at DESC; all assembly is deterministic code, never LLM **[C-IV]**

- [X] T083 [P] [US10] Create `frontend/app/analytics/page.tsx` — analytics dashboard (partner_manager only, route guard): four KPI cards (open matters, upcoming hearings+deadlines, pending invoices, pending AI review); data from `GET /analytics/dashboard`

- [ ] T084 [P] [US10] Create `frontend/app/analytics/financial/page.tsx` — financial report: date range picker, revenue by period bar chart, outstanding invoices table, payment method doughnut chart

- [X] T085 [P] [US10] Create `frontend/app/analytics/operational/page.tsx` — operational report: workload table (lawyer name, active matters count), resolution time distribution bar chart

- [X] T086 [US10] Create `frontend/app/analytics/activity/page.tsx` — activity feed: paginated list of audit_log entries with entity type, action, actor name, timestamp; sourced directly from audit_log — confirms report is grounded in audited facts **[C-III][C-IV]**

---

## Phase 10 — Task Enhancements (FR-142)

**Story goal**: Tasks get priority levels and advanced filtering.
**Independent test**: Create tasks with Low/Medium/High priority; filter by priority, status, assignee, matter, due date — correct subset returned.

- [X] T087 Add `priority TEXT DEFAULT 'medium' CHECK (priority IN ('low','medium','high'))` column to `tasks` table in `supabase/migrations/0017_expansion.sql`; add index on `(priority, status)` for filtering

- [X] T088 [P] Update `backend/app/api/cases.py` (or tasks router) to accept `priority` on create/update and support `?priority=`, `?status=`, `?assignee_id=`, `?matter_id=`, `?due_before=`, `?due_after=` filter params on `GET /tasks`

- [X] T089 [P] Update `frontend/app/tasks/page.tsx` — add priority badge (color-coded: red=high, amber=medium, grey=low), priority filter chip group, and combine with existing status/assignee/matter/date filters

---

## Final Phase — Polish & Integration

Cross-cutting concerns, extended existing screens, smoke test.

- [X] T090 Update `frontend/app/dashboard/page.tsx` — add two new KPI cards: "Upcoming Hearings" (next 7 days count) and "Pending Invoices" (pending/partial count), sourced from `GET /analytics/dashboard`; keep all existing spec 001 cards

- [X] T091 [P] Extend `frontend/app/cases/[id]/page.tsx` (matter detail) — add client link field (searchable select of clients), practice area selector, court/jurisdiction inputs, opposing counsel, docket number, tags input, priority/stage dropdowns; display auto-generated `case_number`

- [X] T092 [P] Extend `frontend/app/cases/page.tsx` (matter list) — add filter options: client, practice area, stage, priority

- [X] T093 [P] Update `frontend/app/settings/page.tsx` — add LLM provider config panel (link to `/app/settings/llm-provider`); add client portal toggle (reads/writes `firm_settings.feature_client_portal`)

- [ ] T094 Apply `supabase/migrations/0017_expansion.sql` to the running instance and confirm all tables, views, sequences, triggers, and RLS policies were created without errors: `psql $DATABASE_URL < supabase/migrations/0017_expansion.sql` then run `\dt` and `\dv` and spot-check each table exists

- [ ] T095 Run end-to-end smoke test from `quickstart.md` steps 1–11: configure LLM provider, create client with conflict check, create extended matter, test DMS check-out/check-in, generate AI draft (verify review gate), create invoice and record payment, create hearing and trigger scheduler reminder, book appointment with conflict detection, log in as portal client and verify scoping, check analytics KPIs match data, verify audit_log completeness

- [ ] T096 Update `specs/002-legal-platform-expansion/spec.md` status field from `Draft` to `Implemented` and note the completion date

---

## Dependency Graph

```
Phase 1 (Setup)
  └─► Phase 2 (Foundation: migration skeleton, sequences, audit, enum extensions)
        └─► Phase 3 (US3: Client Management) ─────────────────────────────────┐
              └─► Phase 4 (US4: DMS) ──────────────────────────────────────── │
                    └─► Phase 5 (US5: Billing) ──────────────────────────────── │
                    └─► Phase 6 (US6/7/8: Hearings+Appointments+Calendar) ─── │
                    └─► Phase 7 (US1/2/11/12/13: AI Document Features) ─────── │
                          ├─────────────────────────────────────────────────── │
Phase 8 (US9: Portal) ◄───┴ Phase 3 + 4 + 5 + 6 + 7 must be complete ────────┘
Phase 9 (US10: Analytics) ◄── all phases must be complete
Phase 10 (Task Enhancements) ◄── independent, can run parallel with Phase 8–9
Final Polish ◄── all phases complete
```

**Key dependency notes**:
- T013 (clients DDL) must precede T007 (cases.client_id FK) — include both in same migration file, clients table first
- T023 (document_templates DDL) must precede T030 (template generate) and T058/T060 (AI doc endpoints)
- T036 (invoices DDL) must precede T071 (portal invoices RLS)
- T052 (hearing scheduler) requires spec 001 scheduler to be running

---

## Parallel Execution Examples

**Phase 3 (US3)** — can run in parallel after T013-T015 (DDL) complete:
- T016 (RLS) ‖ T017 (Pydantic models) → then T018 (API router) → T019 (extend cases) ‖ T020 (frontend list) ‖ T021 (frontend detail)

**Phase 4 (US4)** — after T023-T024 (DDL):
- T025 (RLS) ‖ T026 (models) → T027 (folder/version API) ‖ T028 (checkout API) ‖ T029 (sharing API) ‖ T030 (template API) ‖ T031 (scheduler job)

**Phase 7 (AI features)** — after T056 (LiteLLM dispatch):
- T058 (draft) ‖ T059 (contract review) ‖ T060 (letter pack) ‖ T061 (timeline) ‖ T062 (knowledge search) ‖ T063 (approve endpoint)
- T064 ‖ T065 ‖ T066 ‖ T067 ‖ T068 ‖ T069 (all frontend, no dependencies on each other)

**Phase 8 (Portal)** — after T070-T071 (RLS):
- T072 (API) ‖ T073 (layout/guard) → T074 ‖ T075 ‖ T076 ‖ T077 ‖ T078 (all portal screens)

---

## MVP Scope

Minimum viable delivery is **Phase 3 (US3) only**: client management, conflict check, and extended matter fields. This unlocks client-linked matters and provides immediate operational value while keeping the blast radius small for the first deployment of the expansion migration.

**Phase 3 + Phase 4 + Phase 7** is the recommended first full release: client management + document version control + AI document features together deliver the core legal workflow improvement without billing, portal, or calendar dependencies.
