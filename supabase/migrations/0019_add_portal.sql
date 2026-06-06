-- 0019_add_portal.sql
-- Module G: Client Portal (بوابة العملاء)
-- Read-only client access via time-limited magic links. No Supabase Auth user
-- for clients — instead portal_access + portal_magic_links control entry.

create table portal_access (
    id            uuid        primary key default gen_random_uuid(),
    contact_id    uuid        not null references contacts(id) on delete cascade,
    email         text,
    phone         text,
    is_active     boolean     not null default true,
    last_login_at timestamptz,
    created_at    timestamptz not null default now(),
    unique(contact_id)
);

create index idx_portal_access_contact on portal_access (contact_id);
create index idx_portal_access_phone   on portal_access (phone)  where phone  is not null;
create index idx_portal_access_email   on portal_access (email)  where email  is not null;

create table portal_magic_links (
    id               uuid        primary key default gen_random_uuid(),
    portal_access_id uuid        not null references portal_access(id) on delete cascade,
    token            text        not null unique default encode(gen_random_bytes(32), 'hex'),
    expires_at       timestamptz not null default (now() + interval '24 hours'),
    used_at          timestamptz,
    created_at       timestamptz not null default now()
);

create index idx_portal_links_token on portal_magic_links (token);
create index idx_portal_links_access on portal_magic_links (portal_access_id);

-- Mark portal-visible documents (controlled by staff, not clients)
alter table documents add column if not exists portal_visible boolean not null default false;

create index idx_documents_portal on documents (portal_visible) where portal_visible = true;

-- ── RLS ──────────────────────────────────────────────────────────────────────
-- Portal tables are managed by staff (manager only for portal_access creation).
-- The portal API endpoints use the service_role connection (not app_user) since
-- portal clients authenticate via magic link, not staff JWTs.

alter table portal_access      enable row level security;
alter table portal_magic_links enable row level security;

create policy portal_access_manager on portal_access
    for all to app_user using (rls_is_manager()) with check (rls_is_manager());

create policy portal_access_staff_select on portal_access
    for select to app_user using (not rls_is_manager());

-- magic links: manager only (no direct staff visibility into tokens)
create policy portal_links_manager on portal_magic_links
    for all to app_user using (rls_is_manager()) with check (rls_is_manager());

-- ── audit triggers ───────────────────────────────────────────────────────────
select attach_audit_trigger('portal_access');
select attach_audit_trigger('portal_magic_links');
