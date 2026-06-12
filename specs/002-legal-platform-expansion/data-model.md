# Phase 1 Data Model: Legal Platform Expansion

**Date**: 2026-06-08
**Plan**: [plan.md](plan.md) · **Spec**: [spec.md](spec.md)

Scope: additions and extensions to the **per-firm instance** schema defined in
[spec 001 data-model.md](../001-lawyer-office-management/data-model.md). All existing
spec 001 entities remain unchanged unless explicitly marked **(extends)**. All new tables
are audited (DB triggers, append-only `audit_log`) and RLS-protected. Column types are
finalized in-build; this document is binding on entity shape, relationships, RLS intent,
and state machines.

## Roles (extended)

Existing: `partner_manager` · `lawyer` · `paralegal` · `secretary`
New: **`client`** — portal-only; no access to any non-portal route; RLS restricts all
portal tables to rows linked to the authenticated user's `client_id`.

Manager-only screens: Reports / Analytics, Settings/Admin, Users & Roles, Audit Log viewer.
Portal-only: `/portal/**` routes and `/portal/*` API endpoints.

---

## Extended existing entities

### firm_settings  *(extends)*

New fields:
| Field | Notes |
|---|---|
| `llm_provider_config` | JSONB `{ provider, model, api_key }` — replaces single `llm_api_key`; **secret**, never logged as value **[C-III]** |
| `feature_client_portal` | bool, default `true` — enables client portal for this instance |
| `checkout_timeout_hours` | int, default `24` — auto-release stale checkouts |

### cases (matters) *(extends)*

New fields:
| Field | Notes |
|---|---|
| `client_id` | FK → `clients.id` (nullable for migration compatibility) |
| `case_number` | `text` GENERATED from `cases_number_seq` as `'CASE-' || lpad(nextval(...)::text, 4, '0')`, unique per instance |
| `practice_area` | `text` (free or enum: civil, commercial, family, criminal, real estate, …) |
| `court` | `text` |
| `jurisdiction` | `text` |
| `opposing_counsel` | `text` — also indexed in tsvector for conflict check |
| `docket_number` | `text` |
| `tags` | `text[]` |
| `priority` | `text` CHECK IN ('low', 'medium', 'high'), default `'medium'` |
| `stage` | `text` CHECK IN ('intake', 'active', 'litigation', 'settlement', 'closed'), default `'intake'` |

### users *(extends)*

New fields:
| Field | Notes |
|---|---|
| `role` | extended enum: existing values + `'client'` |
| `client_id` | FK → `clients.id` (only populated when role = `'client'`) — links portal user to client record |

### ai_outputs *(extends)*

New `type` enum values: `doc_draft` · `letter_pack` · `case_timeline`
(existing: `summary` · `extraction` · `analysis` · `clause_flag` · `risk_signal`)

New fields:
| Field | Notes |
|---|---|
| `template_id` | FK → `document_templates.id` (nullable; set for `letter_pack` / `doc_draft` from template) |

All new types follow identical `draft_unreviewed` default, review gate, and source-link
requirements as existing types **[C-II][C-V][C-VI]**.

---

## New entities

### clients

Auto-numbered client records; foundation for matter linking, billing, conflict check,
and portal access.

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `client_number` | `text` GENERATED: `'CL-' || lpad(nextval('clients_number_seq')::text, 6, '0')`, unique per instance |
| `type` | `text` CHECK IN ('individual', 'organization') |
| `name` | `text` NOT NULL — tsvector-indexed for conflict check |
| `conflict_check_notes` | `text` |
| `custom_identifier` | `text` (optional firm-assigned code) |
| `status` | `text` CHECK IN ('active', 'inactive'), default `'active'` |
| `created_by` | FK → `users.id` |
| `created_at` | `timestamptz` DEFAULT now() |

RLS: `partner_manager`, `lawyer`, `paralegal`, `secretary` → read/write own-instance rows.
`client` role → read own row only (WHERE id = auth.client_id).

---

### client_contacts

Multiple typed contacts per client (primary, billing, opposing, witness).

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `client_id` | FK → `clients.id` ON DELETE CASCADE |
| `contact_type` | `text` CHECK IN ('primary', 'billing', 'opposing', 'witness') |
| `name` | `text` NOT NULL — tsvector-indexed for conflict check |
| `phone` | `text` |
| `email` | `text` |
| `address` | `text` |

RLS: same as `clients`.

---

### document_folders

Folder hierarchy for organizing matter documents.

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `matter_id` | FK → `cases.id` |
| `name` | `text` NOT NULL |
| `parent_folder_id` | FK → `document_folders.id` (nullable — root folders have NULL) |
| `created_by` | FK → `users.id` |
| `created_at` | `timestamptz` |

RLS: all non-client roles on own-instance rows.

---

### document_versions

Full version chain for each document. The highest `version_number` for a `document_id`
is the current canonical version.

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `document_id` | FK → `documents.id` |
| `version_number` | `int` NOT NULL |
| `file_path` | `text` (Supabase Storage path for this version) |
| `root_version_id` | FK → `document_versions.id` (nullable — v1 has NULL) |
| `prev_version_id` | FK → `document_versions.id` (nullable — v1 has NULL) |
| `folder_id` | FK → `document_folders.id` (nullable) |
| `access_level` | `text` CHECK IN ('public', 'team', 'restricted'), default `'team'` |
| `is_confidential` | `bool` default `false` — confidential docs never visible in client portal |
| `uploaded_by` | FK → `users.id` |
| `uploaded_at` | `timestamptz` DEFAULT now() |

RLS: `client` role → denied on all `is_confidential = true` rows; otherwise see only
documents with `document_sharing` entry for their `client_id`.
All other roles: own-instance rows with access_level enforcement.

---

### document_checkouts

Pessimistic check-out lock. Unique index on `document_id` prevents double check-out.

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `document_id` | FK → `documents.id` UNIQUE |
| `checked_out_by` | FK → `users.id` |
| `checked_out_at` | `timestamptz` DEFAULT now() |

Stale-release: a scheduler job (or trigger on `users.status` update) DELETEs rows where
`checked_out_at < now() - firm_settings.checkout_timeout_hours * interval '1 hour'`
and writes an audit entry.

---

### document_sharing

Explicit per-client sharing of a document version (only non-confidential allowed).

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `document_id` | FK → `documents.id` |
| `shared_with_client_id` | FK → `clients.id` |
| `shared_by` | FK → `users.id` |
| `shared_at` | `timestamptz` DEFAULT now() |

DB constraint: PREVENT `document_sharing` rows when `document_versions.is_confidential = true`
for the current version of `document_id` (enforced via trigger or CHECK).

---

### document_templates

Reusable document templates for drafts and letter packs. Mustache-style variable substitution
+ AI-filled contextual blocks.

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `name` | `text` NOT NULL |
| `category` | `text` (e.g., `contract`, `submission`, `engagement_letter`, `letter`) |
| `content_template` | `text` — template body with `{{variable}}` and `{{AI: description}}` blocks |
| `variables_schema` | JSONB — `[{ name, source_path, required }]` |
| `created_by` | FK → `users.id` |
| `created_at` | `timestamptz` |

---

### conflict_check_log

Audit trail of all conflict-check runs.

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `checked_by` | FK → `users.id` |
| `checked_at` | `timestamptz` DEFAULT now() |
| `new_party_name` | `text` (the name that was checked) |
| `matched_matter_id` | FK → `cases.id` (nullable — NULL if no match) |
| `matched_party_name` | `text` (nullable) |
| `result` | `text` CHECK IN ('clear', 'conflict_found') |

Append-only (no UPDATE/DELETE). RLS: visible to `partner_manager` and `lawyer` only.

---

### invoices

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `invoice_number` | `text` GENERATED via helper table: `'INV-' || to_char(now(), 'YYYYMM') || '-' || lpad(next_invoice_counter(now())::text, 6, '0')`, unique per instance |
| `matter_id` | FK → `cases.id` (nullable) |
| `client_id` | FK → `clients.id` NOT NULL |
| `status` | `text` CHECK IN ('draft', 'pending', 'partial', 'paid', 'cancelled'), default `'draft'` |
| `subtotal` | `numeric(12,2)` |
| `tax_rate` | `numeric(5,2)` default `14.00` (Egyptian VAT %) |
| `tax_amount` | `numeric(12,2)` GENERATED |
| `discount` | `numeric(12,2)` default `0` |
| `total_due` | `numeric(12,2)` GENERATED |
| `due_date` | `date` |
| `created_by` | FK → `users.id` |
| `created_at` | `timestamptz` |

State machine: `draft` → `pending` (when issued to client) → `partial` (first payment) →
`paid` (fully paid) / `cancelled` (voided). Each transition is audit-logged.

RLS: `partner_manager`, `lawyer` → read/write. `paralegal`, `secretary` → read-only.
`client` role → read own invoices (WHERE client_id = auth.client_id) — portal only.

---

### invoice_items

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `invoice_id` | FK → `invoices.id` ON DELETE CASCADE |
| `description` | `text` NOT NULL |
| `quantity` | `numeric(10,3)` default `1` |
| `unit_price` | `numeric(12,2)` |
| `item_tax_rate` | `numeric(5,2)` nullable (overrides invoice tax_rate if set) |
| `item_discount` | `numeric(12,2)` default `0` |
| `line_total` | `numeric(12,2)` GENERATED |

---

### payments

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `invoice_id` | FK → `invoices.id` |
| `method` | `text` CHECK IN ('cash', 'bank_transfer', 'cheque', 'electronic_wallet', 'card') |
| `amount` | `numeric(12,2)` NOT NULL |
| `payment_date` | `date` NOT NULL |
| `reference` | `text` (cheque number, transfer reference, etc.) |
| `recorded_by` | FK → `users.id` |
| `recorded_at` | `timestamptz` DEFAULT now() |

After INSERT, a trigger re-computes `invoices.status`: if `SUM(payments.amount) >= invoices.total_due`
→ `paid`; else if `SUM > 0` → `partial`.

---

### service_catalog

Reusable line item definitions for quick invoice entry.

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `name` | `text` NOT NULL |
| `default_description` | `text` |
| `default_unit_price` | `numeric(12,2)` |
| `created_by` | FK → `users.id` |

---

### hearings

Court hearings linked to matters. Types are firm-configurable (default: Egyptian civil court).

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `matter_id` | FK → `cases.id` |
| `type` | `text` — default values: `murafa'a` (مرافعة), `taswiya` (تسوية ودية), `tahqiq` (تحقيق), `hukm` (حكم), `ta'jil` (تأجيل), `wasata` (وساطة), `tahkim` (تحكيم), `status_conference`, `other` |
| `court_name` | `text` |
| `court_address` | `text` |
| `courtroom` | `text` |
| `judge` | `text` |
| `docket_number` | `text` |
| `opposing_counsel` | `text` |
| `scheduled_at` | `timestamptz` NOT NULL |
| `status` | `text` CHECK IN ('scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled', 'adjourned'), default `'scheduled'` |
| `reminder_days` | `int` default `3` |
| `assigned_lawyer_id` | FK → `users.id` |
| `notes` | `text` |
| `created_by` | FK → `users.id` |
| `created_at` | `timestamptz` |

RLS: all non-client roles on own-instance rows.
Reminder: deterministic scheduler queries `scheduled_at - reminder_days * '1 day'::interval`;
escalates to `partner_manager` if still `scheduled` (not `confirmed`) within 1 day **[C-IV]**.

---

### appointments

| Field | Notes |
|---|---|
| `id` | uuid PK |
| `type` | `text` CHECK IN ('consultation', 'follow_up', 'checkup', 'emergency') |
| `matter_id` | FK → `cases.id` (nullable) |
| `client_id` | FK → `clients.id` (nullable) |
| `assigned_lawyer_id` | FK → `users.id` NOT NULL |
| `scheduled_at` | `timestamptz` NOT NULL |
| `duration_minutes` | `int` default `60` |
| `status` | `text` CHECK IN ('scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled'), default `'scheduled'` |
| `reason` | `text` |
| `notes` | `text` |
| `created_by` | FK → `users.id` |
| `created_at` | `timestamptz` |

Conflict detection: API layer checks `scheduled_at OVERLAPS (scheduled_at + duration_minutes * '1 min'::interval)`
for the same `assigned_lawyer_id` before INSERT/UPDATE.

RLS: all non-client roles. `client` role → read own appointments via
(WHERE client_id = auth.client_id) — portal only.

---

### invoice_sequences *(helper table for INV numbering)*

| Field | Notes |
|---|---|
| `year_month` | `char(6)` PK (e.g., `'202606'`) |
| `last_counter` | `int` default `0` |

Function `next_invoice_counter(ts)`: `INSERT ... ON CONFLICT DO UPDATE SET last_counter = last_counter + 1 RETURNING last_counter` — atomic under concurrent inserts.

---

## Calendar view (not a table)

```sql
CREATE VIEW calendar_events AS
  SELECT id, 'hearing' AS event_type,
         type AS title, scheduled_at,
         scheduled_at + interval '2 hours' AS end_at,
         matter_id, assigned_lawyer_id, status
  FROM hearings
  UNION ALL
  SELECT id, 'appointment' AS event_type,
         type AS title, scheduled_at,
         scheduled_at + (duration_minutes * interval '1 minute') AS end_at,
         matter_id, assigned_lawyer_id, status
  FROM appointments;
```

RLS is inherited from the underlying tables.

---

## Analytics materialized views

```sql
-- Dashboard KPIs (refreshed on relevant mutations)
CREATE MATERIALIZED VIEW dashboard_kpis AS
SELECT
  (SELECT count(*) FROM cases WHERE stage != 'closed') AS open_matters,
  (SELECT count(*) FROM hearings
   WHERE status IN ('scheduled','confirmed')
     AND scheduled_at BETWEEN now() AND now() + interval '7 days') AS upcoming_hearings,
  (SELECT count(*) FROM deadlines
   WHERE confirmed = true AND due_date BETWEEN now() AND now() + interval '7 days') AS upcoming_deadlines,
  (SELECT count(*) FROM invoices WHERE status IN ('pending','partial')) AS pending_invoices,
  (SELECT count(*) FROM ai_outputs WHERE review_state = 'draft_unreviewed') AS pending_review;
```

Refreshed `CONCURRENTLY` after any DML on: `cases`, `hearings`, `deadlines`, `invoices`, `ai_outputs`.

---

## State machines

### Invoice status
```
draft → pending  (issued/sent to client)
      → cancelled (voided while still draft)
pending → partial  (first payment recorded, total not met)
        → paid     (full payment recorded)
        → cancelled
partial → paid     (remaining payment recorded)
        → cancelled
```
Transitions trigger an audit-log entry each time.

### Document version lifecycle
```
Document checked out → document_checkouts row exists (lock)
                     → other users: check-out attempt fails
                     → owner checks in: new document_versions row, checkout deleted
                     → stale timeout: checkout deleted by scheduler, audit-logged
```

### Hearing status
```
scheduled → confirmed (lawyer acknowledgment)
          → adjourned (hearing rescheduled)
          → cancelled
confirmed → in_progress → completed
          → adjourned
          → cancelled
```

---

## Audit coverage

All new tables receive the same DB-trigger audit pattern as spec 001 (**[C-III]**):
INSERT/UPDATE/DELETE → `audit_log` row (who/role/when/entity/record_id/action/old→new).
`REVOKE UPDATE, DELETE ON audit_log` — append-only enforced at DB level.

Special audit events:
- `document_checkouts` INSERT → `audit_log` action `doc_checkout`
- `document_checkouts` DELETE (check-in) → `audit_log` action `doc_checkin`
- `document_checkouts` DELETE (stale-release) → `audit_log` action `doc_checkout_expired`
- `invoices.status` transition → `audit_log` action `invoice_status_changed`
- `payments` INSERT → `audit_log` action `payment_recorded`
- `conflict_check_log` INSERT → `audit_log` action `conflict_check_run`
- `document_sharing` INSERT/DELETE → `audit_log` action `doc_shared` / `doc_unshared`
