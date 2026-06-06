-- 0015_add_billing.sql
-- Module B: Billing & Invoicing (الفواتير والأتعاب)
-- Time entries, invoices (with line items), and payments.
-- EGP only. Requires Module A (contacts.id used on invoices).

-- ── billing_rates: per-lawyer hourly rate ────────────────────────────────────

create table billing_rates (
    id             uuid        primary key default gen_random_uuid(),
    user_id        uuid        not null references users(id) on delete cascade,
    rate_egp       numeric(12,2) not null check (rate_egp >= 0),
    effective_from date        not null default current_date,
    created_at     timestamptz not null default now(),
    unique(user_id, effective_from)
);

create index idx_billing_rates_user on billing_rates (user_id, effective_from desc);

-- ── invoices (created before time_entries so the FK can reference it) ────────

create type invoice_status as enum (
    'draft', 'sent', 'partial', 'paid', 'cancelled', 'overdue'
);

create table invoices (
    id             uuid           primary key default gen_random_uuid(),
    invoice_number text           not null,           -- INV-2026-0001
    case_id        uuid           references cases(id),
    contact_id     uuid           references contacts(id),
    issue_date     date           not null default current_date,
    due_date       date           not null,
    status         invoice_status not null default 'draft',
    subtotal_egp   numeric(12,2)  not null default 0,
    tax_rate       numeric(5,2)   not null default 14,  -- 14% VAT (Egypt)
    tax_egp        numeric(12,2)  not null default 0,
    discount_egp   numeric(12,2)  not null default 0,
    total_egp      numeric(12,2)  not null default 0,
    notes          text,
    created_by     uuid           references users(id),
    created_at     timestamptz    not null default now(),
    updated_at     timestamptz    not null default now()
);

create index idx_invoices_status     on invoices (status);
create index idx_invoices_contact    on invoices (contact_id);
create index idx_invoices_case       on invoices (case_id);
create index idx_invoices_due        on invoices (due_date) where status not in ('paid','cancelled');

-- Auto-generate invoice numbers (INV-YYYY-NNNN, per instance)
create sequence invoice_seq start 1;

create or replace function next_invoice_number()
returns text language sql as $$
    select 'INV-' || to_char(current_date, 'YYYY') || '-' ||
           lpad(nextval('invoice_seq')::text, 4, '0');
$$;

-- ── invoice_line_items: manual fee lines ─────────────────────────────────────

create table invoice_line_items (
    id              uuid        primary key default gen_random_uuid(),
    invoice_id      uuid        not null references invoices(id) on delete cascade,
    description     text        not null,
    quantity        numeric(10,2) not null default 1 check (quantity > 0),
    unit_price_egp  numeric(12,2) not null,
    total_egp       numeric(12,2) not null,
    sort_order      integer     not null default 0
);

create index idx_invoice_line_items_invoice on invoice_line_items (invoice_id);

-- ── time_entries: billable work logged against a case ────────────────────────

create table time_entries (
    id               uuid        primary key default gen_random_uuid(),
    case_id          uuid        not null references cases(id) on delete cascade,
    user_id          uuid        not null references users(id),
    date             date        not null,
    duration_minutes integer     not null check (duration_minutes > 0),
    description      text        not null,
    is_billable      boolean     not null default true,
    rate_egp         numeric(12,2),          -- snapshot of rate at time of entry
    amount_egp       numeric(12,2),          -- duration/60 * rate
    invoice_id       uuid        references invoices(id) on delete set null,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create index idx_time_entries_case    on time_entries (case_id);
create index idx_time_entries_user    on time_entries (user_id);
create index idx_time_entries_date    on time_entries (date desc);
create index idx_time_entries_invoice on time_entries (invoice_id) where invoice_id is not null;

-- ── payments: partial or full payments against an invoice ────────────────────

create type payment_method as enum ('cash', 'bank_transfer', 'check', 'other');

create table payments (
    id           uuid           primary key default gen_random_uuid(),
    invoice_id   uuid           not null references invoices(id) on delete cascade,
    amount_egp   numeric(12,2)  not null check (amount_egp > 0),
    payment_date date           not null,
    method       payment_method,
    reference    text,                        -- check number / transfer ref
    notes        text,
    recorded_by  uuid           references users(id),
    created_at   timestamptz    not null default now()
);

create index idx_payments_invoice on payments (invoice_id);
create index idx_payments_date    on payments (payment_date desc);

-- ── RLS ──────────────────────────────────────────────────────────────────────

alter table billing_rates    enable row level security;
alter table invoices         enable row level security;
alter table invoice_line_items enable row level security;
alter table time_entries     enable row level security;
alter table payments         enable row level security;

-- billing_rates: manager full access; others read-only
create policy billing_rates_manager on billing_rates
    for all to app_user using (rls_is_manager()) with check (rls_is_manager());
create policy billing_rates_read on billing_rates
    for select to app_user using (not rls_is_manager());

-- invoices: all staff can read; only manager/secretary can write
create policy invoices_select on invoices for select to app_user using (true);
create policy invoices_write on invoices
    for all to app_user
    using (rls_current_role() in ('partner_manager','secretary'))
    with check (rls_current_role() in ('partner_manager','secretary'));

-- line items inherit invoice access
create policy line_items_select on invoice_line_items for select to app_user using (true);
create policy line_items_write on invoice_line_items
    for all to app_user
    using (rls_current_role() in ('partner_manager','secretary'))
    with check (rls_current_role() in ('partner_manager','secretary'));

-- time entries: lawyers/paralegals/secretaries create for assigned cases;
--              managers see all
create policy time_entries_manager on time_entries
    for all to app_user
    using (rls_is_manager()) with check (rls_is_manager());

create policy time_entries_own on time_entries
    for all to app_user
    using (user_id = rls_current_user_id())
    with check (user_id = rls_current_user_id());

create policy time_entries_case_member_select on time_entries
    for select to app_user
    using (rls_assigned_to_case(case_id));

-- payments: manager + secretary
create policy payments_select on payments for select to app_user using (true);
create policy payments_write on payments
    for all to app_user
    using (rls_current_role() in ('partner_manager','secretary'))
    with check (rls_current_role() in ('partner_manager','secretary'));

-- ── audit triggers ───────────────────────────────────────────────────────────
select attach_audit_trigger('billing_rates');
select attach_audit_trigger('invoices');
select attach_audit_trigger('invoice_line_items');
select attach_audit_trigger('time_entries');
select attach_audit_trigger('payments');
