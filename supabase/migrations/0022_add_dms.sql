-- 0022_add_dms.sql
-- Spec 002 gap closure (part 2 of 3): Document Management System (US4).
-- Folder hierarchy, full version control, pessimistic check-in/out,
-- access levels + confidentiality flags, selective client (contact) sharing.
-- Versions are separate Storage objects; document_versions tracks the chain (R2/R3).

-- ── document_folders ─────────────────────────────────────────────────────────

create table document_folders (
    id               uuid        primary key default gen_random_uuid(),
    case_id          uuid        not null references cases(id) on delete cascade,
    name             text        not null,
    parent_folder_id uuid        references document_folders(id) on delete cascade,
    created_by       uuid        references users(id),
    created_at       timestamptz not null default now(),
    unique (case_id, parent_folder_id, name)
);

create index idx_doc_folders_case   on document_folders (case_id);
create index idx_doc_folders_parent on document_folders (parent_folder_id);

-- Documents can live in a folder (null = case root).
alter table documents
    add column if not exists folder_id uuid references document_folders(id) on delete set null,
    add column if not exists access_level text not null default 'team'
        check (access_level in ('public', 'team', 'restricted')),
    add column if not exists is_confidential boolean not null default false;

create index if not exists idx_documents_folder on documents (folder_id);

-- ── document_versions ────────────────────────────────────────────────────────
-- v1 row is created at check-in time for the original upload if absent;
-- documents.file_path always points at the LATEST version's object.

create table document_versions (
    id              uuid        primary key default gen_random_uuid(),
    document_id     uuid        not null references documents(id) on delete cascade,
    version_number  integer     not null check (version_number >= 1),
    file_path       text        not null,
    file_name       text        not null,
    prev_version_id uuid        references document_versions(id),
    uploaded_by     uuid        references users(id),
    uploaded_at     timestamptz not null default now(),
    note            text,
    unique (document_id, version_number)
);

create index idx_doc_versions_doc on document_versions (document_id, version_number desc);

-- ── document_checkouts: pessimistic lock (one row = locked) ─────────────────

create table document_checkouts (
    id              uuid        primary key default gen_random_uuid(),
    document_id     uuid        not null unique references documents(id) on delete cascade,
    checked_out_by  uuid        not null references users(id),
    checked_out_at  timestamptz not null default now()
);

create index idx_doc_checkouts_age on document_checkouts (checked_out_at);

-- ── document_sharing: selective portal sharing per contact ──────────────────
-- Complements documents.portal_visible (0019): a share row scopes visibility
-- to one client contact. Confidential documents can never be shared.

create table document_sharing (
    id          uuid        primary key default gen_random_uuid(),
    document_id uuid        not null references documents(id) on delete cascade,
    contact_id  uuid        not null references contacts(id) on delete cascade,
    shared_by   uuid        references users(id),
    shared_at   timestamptz not null default now(),
    unique (document_id, contact_id)
);

create index idx_doc_sharing_contact on document_sharing (contact_id);

-- DB-level guard: refuse sharing of confidential documents, and refuse
-- marking a shared document confidential without unsharing first.
create or replace function dms_no_confidential_sharing()
returns trigger language plpgsql as $$
begin
    if exists (select 1 from documents d
               where d.id = new.document_id and d.is_confidential) then
        raise exception 'cannot share a confidential document';
    end if;
    return new;
end; $$;

create trigger trg_no_confidential_sharing
    before insert on document_sharing
    for each row execute function dms_no_confidential_sharing();

create or replace function dms_confidential_blocks_existing_shares()
returns trigger language plpgsql as $$
begin
    if new.is_confidential and not old.is_confidential
       and exists (select 1 from document_sharing s where s.document_id = new.id) then
        raise exception 'document has active shares; remove them before marking confidential';
    end if;
    return new;
end; $$;

create trigger trg_confidential_blocks_shares
    before update of is_confidential on documents
    for each row execute function dms_confidential_blocks_existing_shares();

-- ── RLS ──────────────────────────────────────────────────────────────────────
-- Mirrors the documents-table posture: manager everywhere, others on assigned cases.

alter table document_folders   enable row level security;
alter table document_versions  enable row level security;
alter table document_checkouts enable row level security;
alter table document_sharing   enable row level security;

create policy doc_folders_select on document_folders
    for select to app_user using (rls_is_manager() or rls_assigned_to_case(case_id));
create policy doc_folders_write on document_folders
    for all to app_user
    using (rls_is_manager() or rls_assigned_to_case(case_id))
    with check (rls_is_manager() or rls_assigned_to_case(case_id));

create policy doc_versions_select on document_versions
    for select to app_user using (
        rls_is_manager() or exists (
            select 1 from documents d
            where d.id = document_id and rls_assigned_to_case(d.case_id)));
create policy doc_versions_insert on document_versions
    for insert to app_user with check (
        rls_is_manager() or exists (
            select 1 from documents d
            where d.id = document_id and rls_assigned_to_case(d.case_id)));

create policy doc_checkouts_select on document_checkouts
    for select to app_user using (true);  -- lock visibility is global (shows "locked by")
create policy doc_checkouts_write on document_checkouts
    for all to app_user
    using (
        rls_is_manager() or exists (
            select 1 from documents d
            where d.id = document_id and rls_assigned_to_case(d.case_id)))
    with check (
        rls_is_manager() or exists (
            select 1 from documents d
            where d.id = document_id and rls_assigned_to_case(d.case_id)));

create policy doc_sharing_select on document_sharing
    for select to app_user using (
        rls_is_manager() or exists (
            select 1 from documents d
            where d.id = document_id and rls_assigned_to_case(d.case_id)));
create policy doc_sharing_write on document_sharing
    for all to app_user
    using (
        rls_is_manager() or (rls_current_role() = 'lawyer' and exists (
            select 1 from documents d
            where d.id = document_id and rls_assigned_to_case(d.case_id))))
    with check (
        rls_is_manager() or (rls_current_role() = 'lawyer' and exists (
            select 1 from documents d
            where d.id = document_id and rls_assigned_to_case(d.case_id))));

-- ── audit triggers ───────────────────────────────────────────────────────────

select attach_audit_trigger('document_folders');
select attach_audit_trigger('document_versions');
select attach_audit_trigger('document_checkouts');
select attach_audit_trigger('document_sharing');
