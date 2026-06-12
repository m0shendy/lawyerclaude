-- 0017_add_document_templates.sql
-- Module D: Document Templates (نماذج المستندات)
-- Reusable Arabic legal document templates with merge-field tokens.

create type template_category as enum (
    'contract', 'pleading', 'power_of_attorney',
    'letter', 'memo', 'notice', 'court_submission', 'other'
);

create table document_templates (
    id           uuid              primary key default gen_random_uuid(),
    -- firm_id NULL means platform-level (shared across all instances).
    -- For per-firm templates this should be the firm's singleton ID.
    is_platform  boolean           not null default false,
    name_ar      text              not null,
    category     template_category not null,
    -- Arabic template content with {{field_key}} tokens
    content      text              not null,
    -- [{key, label_ar, type, required}] — defines the merge fields
    merge_fields jsonb             not null default '[]'::jsonb,
    is_active    boolean           not null default true,
    version      integer           not null default 1,
    created_by   uuid              references users(id),
    created_at   timestamptz       not null default now(),
    updated_at   timestamptz       not null default now()
);

create index idx_doc_templates_category on document_templates (category);
create index idx_doc_templates_active   on document_templates (is_active);

-- ── RLS ──────────────────────────────────────────────────────────────────────

alter table document_templates enable row level security;

-- All staff can read active templates (platform + per-firm)
create policy templates_select on document_templates
    for select to app_user using (is_active = true);

-- Only manager can create/edit/delete templates
create policy templates_write on document_templates
    for all to app_user
    using (rls_is_manager()) with check (rls_is_manager());

-- ── audit trigger ─────────────────────────────────────────────────────────────
select attach_audit_trigger('document_templates');
