# D:\lawyerclaude — Strategic Expansion Plan

**Date:** June 2026  
**Stack:** Next.js 14 + TypeScript (frontend) · Python 3.12 + FastAPI (backend) · Self-hosted Supabase · Docker + Traefik  
**Target:** Egyptian law firm management SaaS (Arabic RTL, per-firm physical isolation)

---

## 1. Current State Assessment

**Important:** Before planning new work, understand what's already done.

Reviewing `specs/001-lawyer-office-management/tasks.md` shows **all 100 planned tasks are checked** (T001–T100). The platform already includes:

- Full infrastructure: Docker Compose per firm, Traefik routing, Supabase self-hosted, backup scripts, provisioning automation
- Complete DB schema: 13 entities (cases, documents, document_chunks, ai_outputs, deadlines, tasks, notifications_log, reports_log, references_private, audit_log, users, case_assignments, firm_settings)
- Full RBAC with RLS (partner_manager / lawyer / paralegal / secretary)
- Document pipeline: OCR via Google Document AI, Arabic normalization, chunking, pgvector embeddings (HNSW cosine, vector(1536))
- AI features: case summarization, clause extraction, legal reference matching, risk signals, appeal deadline suggestions (feature-flagged), contract analysis
- WhatsApp assistant (WAHA Plus) with conversational RAG
- Deadline tracking with WhatsApp reminders (7d/3d/1d/0d lead, Africa/Cairo scheduler)
- Append-only audit log via DB triggers (REVOKE UPDATE, DELETE enforced)
- All AI outputs born `draft_unreviewed` with mandatory human review gate

**Only two items remain:**
- **T101 FAIL** — Backup restore test failed (Supabase logical restore doesn't cleanly handle event triggers). **This is a production blocker.**
- **T102 deferred** — Per-firm provisioning script hardening

The current spec deliberately excluded: billing/time-tracking, e-filing, and client portals. This plan covers exactly those gaps plus additional features required for a market-complete platform.

---

## 2. Critical Blocker — Fix Before Onboarding Any Real Firm

### T101: Supabase Backup Restore Fix

The issue: Supabase logical dump (`pg_dump --format=custom`) fails to restore when event triggers exist on the schema. The audit_log triggers use `event triggers` (DDL-level), which are not included in logical backups and cause restore errors.

**Fix approach:**

```sql
-- In restore script: drop and recreate event triggers after restore
-- backup/restore.sh additions:

# Before restore:
psql $TARGET_URL -c "SELECT pg_catalog.pg_drop_trigger_name..."
# Actually: event triggers must be dropped before restore, recreated after

# 1. Export event trigger definitions separately
pg_dump --schema-only --section=post-data $SOURCE_URL \
  | grep -A 20 'CREATE EVENT TRIGGER' > event_triggers.sql

# 2. Logical restore without event triggers
pg_restore --no-privileges --no-owner \
  --exclude-table-data=audit_log \
  -d $TARGET_URL dump.custom

# 3. Reapply event triggers
psql $TARGET_URL -f event_triggers.sql
```

Alternative (simpler): Replace the DDL event trigger with a standard row-level trigger on each table. Row-level triggers ARE included in logical backups. The audit log append-only constraint is then enforced via `REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC` (already done) and the trigger becomes a normal `AFTER INSERT OR UPDATE OR DELETE` trigger — which pg_dump handles correctly.

**Recommended action:** Convert DDL event triggers to row-level triggers on each audited table. This unblocks T101 and simplifies the backup/restore pipeline.

---

## 3. Expansion Feature Map

The following 8 feature modules bring the platform to "complete" for an Egyptian law firm. They are ordered by dependency — later modules build on earlier ones.

### Module A: Contacts & Parties Registry (الأطراف والجهات)

**What:** A shared address book for people and organizations connected to cases — clients, opposing parties, opposing counsel, courts, judges, notaries, government agencies.

**Why first:** Several later modules (billing, hearings, correspondence) need a `contact_id` reference. Building contacts first avoids retrofitting.

**New DB tables:**

```sql
-- contacts: any person or organization the firm interacts with
CREATE TABLE contacts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id         uuid NOT NULL REFERENCES firm_settings(id) ON DELETE CASCADE,
  type            text NOT NULL CHECK (type IN (
                    'client','opposing_party','opposing_counsel',
                    'court','judge','notary','government','expert','other'
                  )),
  name_ar         text NOT NULL,                -- Arabic full name
  name_en         text,
  national_id     text,                         -- رقم قومي (individuals)
  tax_id          text,                         -- للشركات
  phone           text,
  email           text,
  address         text,
  notes           text,
  is_active       boolean NOT NULL DEFAULT true,
  created_by      uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- case_contacts: link a contact to a case with their role in that case
CREATE TABLE case_contacts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id         uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  contact_id      uuid NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  role            text NOT NULL CHECK (role IN (
                    'client','opposing_party','opposing_counsel',
                    'witness','expert','court','other'
                  )),
  notes           text,
  added_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE(case_id, contact_id, role)
);

-- RLS: firm_id isolation
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY contacts_firm_isolation ON contacts
  USING (firm_id = current_setting('app.current_firm_id')::uuid);
```

**FastAPI endpoints:**
```
GET    /contacts?type=&search=
POST   /contacts
GET    /contacts/{id}
PATCH  /contacts/{id}
DELETE /contacts/{id}        (soft-delete: is_active=false)

GET    /cases/{case_id}/contacts
POST   /cases/{case_id}/contacts         (link existing or create+link)
DELETE /cases/{case_id}/contacts/{id}    (unlink)
```

**Frontend pages:**
- `/contacts` — searchable list with type filter badges, RTL table
- `/contacts/[id]` — detail card + linked cases list
- `/contacts/new` — creation form

**Build order:** A before everything else.

---

### Module B: Billing & Invoicing (الفواتير والأتعاب)

**What:** Time entries, invoices, payment recording, outstanding balance tracking. Supports both hourly billing and flat-fee matters. EGP only.

**New DB tables:**

```sql
-- billing_rates: per-lawyer hourly rate within a firm
CREATE TABLE billing_rates (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id     uuid NOT NULL REFERENCES firm_settings(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rate_egp    numeric(12,2) NOT NULL,
  effective_from date NOT NULL DEFAULT CURRENT_DATE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE(firm_id, user_id, effective_from)
);

-- time_entries: billable and non-billable work logged against a case
CREATE TABLE time_entries (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id         uuid NOT NULL REFERENCES firm_settings(id) ON DELETE CASCADE,
  case_id         uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  user_id         uuid NOT NULL REFERENCES users(id),
  date            date NOT NULL,
  duration_minutes integer NOT NULL CHECK (duration_minutes > 0),
  description     text NOT NULL,
  is_billable     boolean NOT NULL DEFAULT true,
  rate_egp        numeric(12,2),               -- snapshot of rate at time of entry
  amount_egp      numeric(12,2),               -- computed: duration/60 * rate
  invoice_id      uuid,                        -- FK added after invoices table exists
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- invoices
CREATE TABLE invoices (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id         uuid NOT NULL REFERENCES firm_settings(id) ON DELETE CASCADE,
  invoice_number  text NOT NULL,               -- INV-2026-0001, auto-generated
  case_id         uuid REFERENCES cases(id),
  contact_id      uuid REFERENCES contacts(id),-- client being billed (Module A)
  issue_date      date NOT NULL DEFAULT CURRENT_DATE,
  due_date        date NOT NULL,
  status          text NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','sent','partial','paid','cancelled','overdue')),
  subtotal_egp    numeric(12,2) NOT NULL DEFAULT 0,
  tax_rate        numeric(5,2) NOT NULL DEFAULT 14,  -- 14% VAT default (Egypt)
  tax_egp         numeric(12,2) NOT NULL DEFAULT 0,
  discount_egp    numeric(12,2) NOT NULL DEFAULT 0,
  total_egp       numeric(12,2) NOT NULL DEFAULT 0,
  notes           text,
  created_by      uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- invoice_line_items: manual fee lines (not from time entries)
CREATE TABLE invoice_line_items (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id      uuid NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  description     text NOT NULL,
  quantity        numeric(10,2) NOT NULL DEFAULT 1,
  unit_price_egp  numeric(12,2) NOT NULL,
  total_egp       numeric(12,2) NOT NULL,
  sort_order      integer NOT NULL DEFAULT 0
);

-- payments: partial or full payments against an invoice
CREATE TABLE payments (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id         uuid NOT NULL REFERENCES firm_settings(id) ON DELETE CASCADE,
  invoice_id      uuid NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  amount_egp      numeric(12,2) NOT NULL,
  payment_date    date NOT NULL,
  method          text CHECK (method IN ('cash','bank_transfer','check','other')),
  reference       text,                        -- check number / transfer ref
  notes           text,
  recorded_by     uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Add FK from time_entries to invoices
ALTER TABLE time_entries
  ADD CONSTRAINT time_entries_invoice_fk
  FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE SET NULL;

-- RLS policies (same firm_id pattern)
ALTER TABLE time_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
```

**RBAC rules:**
- `partner_manager`: full CRUD on all billing
- `lawyer`: create/view own time entries; view invoices for assigned cases
- `paralegal`: create time entries for assigned cases; view invoices
- `secretary`: create time entries; create invoice drafts; record payments

**FastAPI endpoints:**
```
# Time entries
GET    /time-entries?case_id=&user_id=&from=&to=
POST   /time-entries
PATCH  /time-entries/{id}
DELETE /time-entries/{id}

# Invoices
GET    /invoices?status=&case_id=&contact_id=
POST   /invoices                             (creates with line items)
GET    /invoices/{id}
PATCH  /invoices/{id}
POST   /invoices/{id}/send                   (status: draft → sent, send WhatsApp/email)
POST   /invoices/{id}/cancel
GET    /invoices/{id}/pdf                    (generate PDF)

# Payments
POST   /invoices/{id}/payments
GET    /invoices/{id}/payments
```

**Frontend pages:**
- `/billing` — outstanding invoices dashboard (overdue highlighted, aging summary)
- `/billing/invoices` — full invoice list with status filters
- `/billing/invoices/new` — create invoice, add time entries or manual lines
- `/billing/invoices/[id]` — invoice detail, payment history, record payment button
- `/billing/time` — time entry log grouped by case and lawyer
- `/billing/rates` — billing rates management (partner_manager only)

**Build order:** Requires Module A (contacts) for `contact_id` on invoices.

---

### Module C: Court Hearings (الجلسات)

**What:** Track scheduled court sessions per case, the presiding court/judge, results, and next hearing date. This is the highest-frequency daily workflow for Egyptian lawyers.

**New DB table:**

```sql
CREATE TABLE hearings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id         uuid NOT NULL REFERENCES firm_settings(id) ON DELETE CASCADE,
  case_id         uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  hearing_date    timestamptz NOT NULL,
  court_name      text NOT NULL,               -- اسم المحكمة
  court_room      text,                        -- قاعة / دائرة
  judge_contact_id uuid REFERENCES contacts(id), -- Module A
  assigned_lawyer_id uuid REFERENCES users(id),
  status          text NOT NULL DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled','held','adjourned','cancelled')),
  -- Outcome (filled after session)
  result          text,                        -- نتيجة الجلسة
  next_hearing_date timestamptz,
  next_hearing_court text,
  notes           text,
  -- Reminder tracking
  reminder_sent_7d  boolean DEFAULT false,
  reminder_sent_3d  boolean DEFAULT false,
  reminder_sent_1d  boolean DEFAULT false,
  reminder_sent_0d  boolean DEFAULT false,
  created_by      uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE hearings ENABLE ROW LEVEL SECURITY;
CREATE POLICY hearings_firm_isolation ON hearings
  USING (firm_id = current_setting('app.current_firm_id')::uuid);
```

**Integration with existing scheduler:** The deadline reminder scheduler (already built, runs at 08:00/08:30 Africa/Cairo) can be extended to query `hearings` alongside `deadlines` using the same lead-time logic (7d/3d/1d/0d) and the same `notifications_log` table.

```python
# backend/app/scheduler/hearing_reminders.py
# Extends existing deadline_reminders.py pattern

async def send_hearing_reminders():
    today = date.today()
    for lead_days, field in [(7,"reminder_sent_7d"),(3,"reminder_sent_3d"),
                              (1,"reminder_sent_1d"),(0,"reminder_sent_0d")]:
        target_date = today + timedelta(days=lead_days)
        hearings = await db.fetch(
            f"""SELECT h.*, c.case_number, c.title, u.phone, u.name_ar
                FROM hearings h
                JOIN cases c ON h.case_id = c.id
                JOIN users u ON h.assigned_lawyer_id = u.id
                WHERE h.hearing_date::date = $1
                  AND h.status = 'scheduled'
                  AND h.{field} = false
                  AND h.firm_id = $2""",
            target_date, firm_id
        )
        for h in hearings:
            await send_whatsapp(h['phone'],
                f"تذكير جلسة: قضية {h['case_number']} - {h['court_name']} "
                f"بتاريخ {h['hearing_date'].strftime('%Y-%m-%d')}")
            await db.execute(f"UPDATE hearings SET {field}=true WHERE id=$1", h['id'])
```

**FastAPI endpoints:**
```
GET    /cases/{case_id}/hearings
POST   /cases/{case_id}/hearings
PATCH  /hearings/{id}               (update outcome, next date)
DELETE /hearings/{id}

GET    /hearings/upcoming?days=30   (cross-case calendar view)
```

**Frontend pages:**
- `/hearings` — weekly/monthly calendar view of all upcoming hearings, color-coded by case
- `/cases/[id]/hearings` — tab within case detail, timeline of past + upcoming hearings
- Hearing form: embedded in case detail page, not a separate route

**Build order:** Can be built independently of B. Needs A only for judge contact link (optional FK — can be a text field initially).

---

### Module D: Document Templates (نماذج المستندات)

**What:** A library of reusable Arabic legal document templates with merge fields. When creating a document, the lawyer picks a template and the system auto-fills case/party/date fields.

**New DB tables:**

```sql
CREATE TABLE document_templates (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id         uuid,                        -- NULL = platform-level template
  name_ar         text NOT NULL,
  category        text NOT NULL CHECK (category IN (
                    'contract','pleading','power_of_attorney',
                    'letter','memo','notice','court_submission','other'
                  )),
  content         text NOT NULL,               -- Arabic template with {{field}} tokens
  merge_fields    jsonb NOT NULL DEFAULT '[]'::jsonb,
                                               -- [{key, label_ar, type, required}]
  is_active       boolean NOT NULL DEFAULT true,
  version         integer NOT NULL DEFAULT 1,
  created_by      uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Merge field token examples in content:
-- {{case_number}}, {{client_name_ar}}, {{court_name}},
-- {{hearing_date}}, {{lawyer_name}}, {{today}}
```

**Template merge engine (Python):**
```python
# backend/app/services/template_service.py
import re
from datetime import date

SYSTEM_FIELDS = {
    "today": lambda ctx: date.today().strftime("%Y/%m/%d"),
    "case_number": lambda ctx: ctx["case"]["case_number"],
    "case_title": lambda ctx: ctx["case"]["title"],
    "client_name_ar": lambda ctx: ctx["client"]["name_ar"],
    "lawyer_name": lambda ctx: ctx["lawyer"]["name_ar"],
    "court_name": lambda ctx: ctx.get("hearing", {}).get("court_name", ""),
    "hearing_date": lambda ctx: ctx.get("hearing", {}).get("hearing_date", ""),
}

def render_template(template_content: str, context: dict, overrides: dict = {}) -> str:
    result = template_content
    merged = {**{k: v(context) for k, v in SYSTEM_FIELDS.items()}, **overrides}
    for key, value in merged.items():
        result = result.replace(f"{{{{{key}}}}}", str(value or ""))
    # Warn on any unresolved tokens
    unresolved = re.findall(r'\{\{(\w+)\}\}', result)
    if unresolved:
        raise ValueError(f"Unresolved template fields: {unresolved}")
    return result
```

**FastAPI endpoints:**
```
GET    /templates?category=
POST   /templates
GET    /templates/{id}
PATCH  /templates/{id}

POST   /templates/{id}/render    (body: {case_id, overrides})
       → returns rendered text, caller saves as new document
```

**Frontend pages:**
- `/templates` — library grid grouped by category, with preview
- `/templates/new` — rich text editor with Arabic RTL support + merge field inserter
- Integration: `/documents/new` gains a "From Template" button that opens template picker

**Build order:** D is independent. Can be built in parallel with B and C.

---

### Module E: Correspondence Log (المراسلات)

**What:** Track all external communications per case — letters sent, emails received, court submissions, etc. Provides a communication timeline alongside the document list.

**New DB table:**

```sql
CREATE TABLE correspondence (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id         uuid NOT NULL REFERENCES firm_settings(id) ON DELETE CASCADE,
  case_id         uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  direction       text NOT NULL CHECK (direction IN ('inbound','outbound')),
  channel         text NOT NULL CHECK (channel IN (
                    'email','letter','fax','whatsapp','phone','court','other'
                  )),
  subject         text NOT NULL,
  body_summary    text,                        -- brief summary, not full content
  document_id     uuid REFERENCES documents(id),  -- attached document if any
  contact_id      uuid REFERENCES contacts(id),   -- who sent/received (Module A)
  sent_received_at timestamptz NOT NULL DEFAULT now(),
  recorded_by     uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE correspondence ENABLE ROW LEVEL SECURITY;
CREATE POLICY correspondence_firm_isolation ON correspondence
  USING (firm_id = current_setting('app.current_firm_id')::uuid);
```

**FastAPI endpoints:**
```
GET    /cases/{case_id}/correspondence
POST   /cases/{case_id}/correspondence
PATCH  /correspondence/{id}
DELETE /correspondence/{id}
```

**Frontend:** Tab within case detail page — a chronological timeline view with direction badges (inbound/outbound), channel icons, and expandable summary.

**Build order:** Depends on A for contact_id. Otherwise independent.

---

### Module F: Financial Dashboard (التقارير المالية)

**What:** Aggregate billing views for the partner: monthly revenue, outstanding receivables, per-lawyer productivity, per-case profitability. Built on top of Module B data.

**No new tables.** This module is a set of read-only analytics endpoints and a dashboard page querying the billing tables.

**FastAPI endpoints:**
```python
# backend/app/routers/analytics.py

GET /analytics/revenue
    # params: from, to, group_by=month|week|lawyer|practice_area
    # returns: [{period, billed_egp, collected_egp, outstanding_egp}]

GET /analytics/aging
    # Accounts receivable aging: 0-30, 31-60, 61-90, 90+ days overdue
    # returns: [{bucket, count, total_egp, invoices: [{id, contact, amount}]}]

GET /analytics/lawyer-productivity
    # params: from, to
    # returns: [{user_id, name, hours_logged, billable_hours,
    #            billed_egp, collected_egp, utilization_rate}]

GET /analytics/case-profitability
    # params: case_id (optional — returns all if omitted)
    # returns: [{case_id, case_number, title, total_billed, total_collected,
    #            time_value, margin}]
```

**Frontend page:**
- `/analytics` — Partner-only dashboard with 4 KPI cards + 3 charts (revenue trend, aging donut, lawyer utilization bar) + exportable tables

**Build order:** Requires Module B to be complete.

---

### Module G: Client Portal (بوابة العملاء)

**What:** A separate read-only login for clients to view their case status, upcoming hearings, documents shared with them, and outstanding invoices.

**Architecture note:** Given the per-firm physical isolation design, the client portal should be a separate Next.js route group (`/portal/...`) within the same Next.js app, protected by a separate `portal_sessions` auth mechanism (not the staff JWT). Clients have no Supabase Auth user; instead, a time-limited magic link is generated and sent via WhatsApp/email.

**New DB tables:**

```sql
CREATE TABLE portal_access (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_id         uuid NOT NULL REFERENCES firm_settings(id) ON DELETE CASCADE,
  contact_id      uuid NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  email           text,
  phone           text,
  is_active       boolean NOT NULL DEFAULT true,
  last_login_at   timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE portal_magic_links (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  portal_access_id uuid NOT NULL REFERENCES portal_access(id) ON DELETE CASCADE,
  token           text NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(32), 'hex'),
  expires_at      timestamptz NOT NULL DEFAULT (now() + interval '24 hours'),
  used_at         timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- What data the portal exposes per contact
-- Controlled by case_contacts.role = 'client' — portal shows cases
-- where this contact is linked as 'client'
-- Documents: only documents explicitly marked portal_visible=true
ALTER TABLE documents ADD COLUMN portal_visible boolean NOT NULL DEFAULT false;
```

**FastAPI endpoints (portal namespace — no staff JWT required, uses portal token):**
```
POST   /portal/auth/request-link    (body: {phone or email} → sends magic link)
POST   /portal/auth/verify          (body: {token} → returns portal_session JWT)

GET    /portal/cases                (cases where contact is client)
GET    /portal/cases/{id}           (case summary, hearings, tasks)
GET    /portal/documents            (portal_visible=true docs for client's cases)
GET    /portal/invoices             (invoices for client contact)
```

**Frontend route group:** `/portal/login`, `/portal/dashboard`, `/portal/cases/[id]`

**Build order:** Requires A (contacts), C (hearings), B (invoices), E (correspondence). Build last.

---

### Module H: Advanced Reporting (التقارير المتقدمة)

**What:** Exportable management reports beyond the existing daily manager digest — case status summary, matter aging, team workload, deadline compliance rate.

**No new tables.** Queries across existing + new module tables.

**FastAPI endpoints:**
```
GET /reports/case-summary?from=&to=&status=&practice_area=
GET /reports/deadline-compliance?from=&to=&user_id=
GET /reports/workload?from=&to=       # tasks + hearings + deadlines per lawyer
GET /reports/export/{report_type}?format=xlsx|pdf
```

**Frontend:** `/reports` page with report type selector and date range picker. Export buttons call the `/export` endpoint.

**Build order:** Depends on all modules for full data. Can be done incrementally.

---

## 4. Build Order (Dependency Graph)

```
[T101 FIX] ──────────────────────────────────────────── (unblocks real firm onboarding)
     │
     └── Phase 14: Module A (Contacts & Parties)
              │
         ┌───┴──────────────────────┐
         │                          │
  Phase 15: Module B (Billing)   Phase 16: Module C (Hearings)
         │                          │
         └───────────┬──────────────┘
                     │
             Phase 17: Module D (Templates)  ← can run in parallel with 15/16
             Phase 18: Module E (Correspondence) ← needs A; runs after A
                     │
             Phase 19: Module F (Financial Dashboard) ← needs B
                     │
             Phase 20: Module G (Client Portal) ← needs A, B, C, E
                     │
             Phase 21: Module H (Advanced Reporting) ← needs all
```

**Parallelizable work:**
- D (Templates) has no dependencies — can be started immediately after A
- C (Hearings) and B (Billing) can be built in parallel after A
- E (Correspondence) needs only A — can run in parallel with B and C

---

## 5. DB Migration Files

Each module should be a numbered migration. Suggested naming:

```
supabase/migrations/
  0001_..._initial_schema.sql          # existing
  ...
  0014_add_contacts.sql                # Module A
  0015_add_billing.sql                 # Module B
  0016_add_hearings.sql                # Module C
  0017_add_document_templates.sql      # Module D
  0018_add_correspondence.sql          # Module E
  0019_add_portal.sql                  # Module G
```

Each migration file follows the existing pattern: `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`, `ALTER TABLE ENABLE ROW LEVEL SECURITY`, `CREATE POLICY`.

---

## 6. Frontend Architecture Notes

All new pages follow the existing conventions in `D:\lawyerclaude\frontend`:

- **RTL layout** via `dir="rtl"` on root + Tailwind `rtl:` utilities
- **Arabic labels** defined in `frontend/lib/types.ts` (add new enums there)
- **API calls** via `frontend/lib/api.ts` (add new resource clients there)
- **Form validation** with react-hook-form + zod (existing pattern)
- **Tables** with existing DataTable component

New route structure to add in `frontend/app/`:
```
app/
  contacts/
    page.tsx          → contact list
    [id]/page.tsx     → contact detail
    new/page.tsx      → create contact
  billing/
    page.tsx          → billing dashboard
    invoices/
      page.tsx
      new/page.tsx
      [id]/page.tsx
    time/page.tsx
    rates/page.tsx
  hearings/
    page.tsx          → calendar view
  templates/
    page.tsx
    new/page.tsx
    [id]/page.tsx
  correspondence/     → accessed via case detail tab only
  analytics/page.tsx
  reports/page.tsx
  portal/             → separate layout (no staff nav)
    login/page.tsx
    dashboard/page.tsx
    cases/[id]/page.tsx
```

---

## 7. FastAPI Backend Structure

Add new routers to `backend/app/main.py`:

```python
from app.routers import (
    contacts,        # Module A
    billing,         # Module B  
    hearings,        # Module C
    templates,       # Module D
    correspondence,  # Module E
    analytics,       # Module F
    portal,          # Module G
    reports,         # Module H
)

app.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
app.include_router(billing.router, prefix="", tags=["billing"])
app.include_router(hearings.router, prefix="", tags=["hearings"])
app.include_router(templates.router, prefix="/templates", tags=["templates"])
app.include_router(correspondence.router, prefix="", tags=["correspondence"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(portal.router, prefix="/portal", tags=["portal"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
```

Each router file follows the existing pattern:
```python
# backend/app/routers/contacts.py
from fastapi import APIRouter, Depends
from app.dependencies import get_firm_id, require_role
from app.schemas.contacts import ContactCreate, ContactRead, ContactUpdate
from app.services.contacts import ContactService

router = APIRouter()

@router.get("/", response_model=list[ContactRead])
async def list_contacts(
    type: str | None = None,
    search: str | None = None,
    firm_id: str = Depends(get_firm_id),
):
    return await ContactService.list(firm_id=firm_id, type=type, search=search)
```

---

## 8. Cost Impact

The per-firm Docker + Supabase architecture means each new module adds:
- Storage: contacts/billing/hearings rows — negligible per firm
- pgvector: no new embeddings in A/B/C/E/F/H; only D (templates) may add embeddings for template search — optional
- Compute: hearing reminders add ~10ms to the existing scheduler run; analytics endpoints add one-time query cost per page load

**No change to the ~$22-30/firm/month fixed floor** for firms under 100 cases. Billing module could add Pandoc/WeasyPrint for PDF invoice generation — add to Docker Compose as a separate container.

---

## 9. Constitutional Constraints (from CLAUDE.md)

All new modules must respect these invariants from the existing project:

1. **Append-only audit_log** — every write to new tables must fire the existing audit trigger (extend `audited_tables` list in trigger setup)
2. **AI outputs born draft_unreviewed** — if D (templates) adds AI-assisted draft generation, the output must go through `ai_outputs` with `review_state = 'draft_unreviewed'`
3. **No cross-firm data** — every new table gets `firm_id` + RLS policy using `current_setting('app.current_firm_id')`
4. **Arabic normalization** — any new Arabic text search (contacts name, template content) must pass through `normalize_arabic()` before indexing
5. **Human review gate** — billing amounts computed by AI (e.g., auto-suggested invoice from time entries) must be reviewed before sending to client
6. **Feature flags** — any legally sensitive feature (e.g., automated invoice sending) should be behind a feature flag in `firm_settings`

---

## 10. Suggested Implementation Prompts for Claude Code

When working on each module with Claude Code, provide the following context at the start of each session:

**For any new DB migration:**
```
Read D:\lawyerclaude\CLAUDE.md, specs/001-lawyer-office-management/data-model.md,
and supabase/migrations/[latest].sql first. Then create migration 00NN_add_[module].sql
following the exact same pattern: CREATE TABLE with firm_id, ENABLE ROW LEVEL SECURITY,
CREATE POLICY using current_setting('app.current_firm_id'), add to audit trigger list.
```

**For any new FastAPI router:**
```
Read D:\lawyerclaude\CLAUDE.md and backend/app/routers/[existing_router].py first.
Create backend/app/routers/[new_router].py following the same dependency injection
pattern (get_firm_id, require_role), same error handling, same Pydantic schema structure.
Add to backend/app/main.py includes.
```

**For any new frontend page:**
```
Read D:\lawyerclaude\CLAUDE.md and frontend/lib/types.ts and
frontend/app/[similar_page]/page.tsx first. Create the new page using Arabic RTL layout,
existing UI components, and the types pattern. Add Arabic labels to frontend/lib/types.ts.
```

---

## 11. Quick Reference — New Tables Summary

| Table | Module | Depends on |
|---|---|---|
| contacts | A | firm_settings, users |
| case_contacts | A | contacts, cases |
| billing_rates | B | firm_settings, users |
| time_entries | B | firm_settings, cases, users |
| invoices | B | firm_settings, cases, contacts |
| invoice_line_items | B | invoices |
| payments | B | firm_settings, invoices |
| hearings | C | firm_settings, cases, contacts, users |
| document_templates | D | firm_settings, users |
| correspondence | E | firm_settings, cases, contacts, documents |
| portal_access | G | firm_settings, contacts |
| portal_magic_links | G | portal_access |

**Columns added to existing tables:**
- `documents.portal_visible boolean` (Module G)

---

## 12. Out of Scope (Intentionally)

The following remain out of scope even in this expansion, consistent with the original spec rationale:

- **E-filing / court system integration** — No stable Egyptian court API exists as of 2026; manual data entry via Module C is the right approach
- **IOLTA / trust accounting** — Separate bank account tracking for client funds; requires accounting expertise and auditor sign-off; out of scope for v1 billing
- **Multi-currency** — EGP only; Egyptian civil law firms don't typically bill in foreign currencies
- **Time-tracking timers** — Real-time stopwatch timers add mobile complexity; manual minute entry is sufficient for v1
- **Email integration (IMAP/SMTP)** — Correspondence log (Module E) uses manual entry; full email sync adds significant security surface area and is deferred

---

*End of expansion plan. Total new tables: 12. Total new API endpoint groups: 8. Estimated implementation time with Claude Code: 6–8 sessions of 2–3 hours each, following the build order above.*
