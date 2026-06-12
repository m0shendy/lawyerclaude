-- 0018_add_correspondence.sql
-- Module E: Correspondence Log (المراسلات)
-- Tracks all external communications per case — letters, emails, court filings, etc.

create type correspondence_direction as enum ('inbound', 'outbound');
create type correspondence_channel   as enum (
    'email', 'letter', 'fax', 'whatsapp', 'phone', 'court', 'other'
);

create table correspondence (
    id               uuid                     primary key default gen_random_uuid(),
    case_id          uuid                     not null references cases(id) on delete cascade,
    direction        correspondence_direction not null,
    channel          correspondence_channel   not null,
    subject          text                     not null,
    body_summary     text,                                    -- brief summary only
    document_id      uuid                     references documents(id),
    contact_id       uuid                     references contacts(id),
    sent_received_at timestamptz              not null default now(),
    recorded_by      uuid                     references users(id),
    created_at       timestamptz              not null default now()
);

create index idx_correspondence_case on correspondence (case_id, sent_received_at desc);
create index idx_correspondence_contact on correspondence (contact_id) where contact_id is not null;

-- ── RLS ──────────────────────────────────────────────────────────────────────

alter table correspondence enable row level security;

create policy correspondence_manager on correspondence
    for all to app_user using (rls_is_manager()) with check (rls_is_manager());

create policy correspondence_case_member_select on correspondence
    for select to app_user using (rls_assigned_to_case(case_id));

create policy correspondence_case_member_write on correspondence
    for all to app_user
    using (rls_assigned_to_case(case_id) and rls_current_role() in ('lawyer','paralegal','secretary'))
    with check (rls_assigned_to_case(case_id) and rls_current_role() in ('lawyer','paralegal','secretary'));

-- ── audit trigger ─────────────────────────────────────────────────────────────
select attach_audit_trigger('correspondence');
