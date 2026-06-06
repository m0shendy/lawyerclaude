-- 0014_add_contacts.sql
-- Module A: Contacts & Parties Registry (الأطراف والجهات)
-- Shared address book for all people/orgs the firm interacts with.
-- Required by: billing (invoices.contact_id), hearings (judge_contact_id),
--              correspondence (contact_id), portal (portal_access.contact_id).

-- ── contacts: any person or organisation ────────────────────────────────────

create type contact_type as enum (
    'client', 'opposing_party', 'opposing_counsel',
    'court', 'judge', 'notary', 'government', 'expert', 'other'
);

create type contact_case_role as enum (
    'client', 'opposing_party', 'opposing_counsel',
    'witness', 'expert', 'court', 'other'
);

create table contacts (
    id            uuid        primary key default gen_random_uuid(),
    type          contact_type not null,
    name_ar       text        not null,           -- Arabic full name (required)
    name_en       text,
    national_id   text,                           -- رقم قومي (individuals)
    tax_id        text,                           -- للشركات
    phone         text,
    email         text,
    address       text,
    notes         text,
    name_ar_tsvec tsvector generated always as (to_tsvector('arabic', name_ar)) stored,
    is_active     boolean     not null default true,
    created_by    uuid        references users(id),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index idx_contacts_type       on contacts (type);
create index idx_contacts_name_fts   on contacts using gin(name_ar_tsvec);
create index idx_contacts_active     on contacts (is_active);
create index idx_contacts_national   on contacts (national_id) where national_id is not null;

-- ── case_contacts: link a contact to a case with their role in that case ─────

create table case_contacts (
    id         uuid              primary key default gen_random_uuid(),
    case_id    uuid              not null references cases(id) on delete cascade,
    contact_id uuid              not null references contacts(id) on delete cascade,
    role       contact_case_role not null,
    notes      text,
    added_at   timestamptz       not null default now(),
    unique(case_id, contact_id, role)
);

create index idx_case_contacts_case    on case_contacts (case_id);
create index idx_case_contacts_contact on case_contacts (contact_id);

-- ── RLS ──────────────────────────────────────────────────────────────────────
-- Per-instance isolation: all staff can read active contacts; only manager
-- can hard-delete or permanently deactivate; lawyers+ can create/edit.

alter table contacts      enable row level security;
alter table case_contacts enable row level security;

-- contacts: all authenticated staff can read; non-manager can write their own
create policy contacts_select on contacts
    for select to app_user using (true);

create policy contacts_insert on contacts
    for insert to app_user
    with check (rls_current_role() is not null);  -- any logged-in role

create policy contacts_update on contacts
    for update to app_user
    using (rls_current_role() is not null)
    with check (rls_current_role() is not null);

create policy contacts_delete on contacts
    for delete to app_user
    using (rls_is_manager());  -- hard delete: manager only (soft-delete via is_active)

-- case_contacts: mirrors case access (if you see the case, you see its parties)
create policy case_contacts_select on case_contacts
    for select to app_user using (true);

create policy case_contacts_insert on case_contacts
    for insert to app_user
    with check (rls_current_role() is not null);

create policy case_contacts_delete on case_contacts
    for delete to app_user
    using (rls_is_manager() or rls_assigned_to_case(case_id));

-- ── audit triggers ───────────────────────────────────────────────────────────
select attach_audit_trigger('contacts');
select attach_audit_trigger('case_contacts');
