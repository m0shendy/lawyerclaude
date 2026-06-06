-- 0002_core_schema.sql
-- Core schema for one firm instance: 13 entities per data-model.md.
-- Every table here (except read-only/shared concerns) is audited (0005) and
-- RLS-protected by in-instance role (0007). Cross-firm isolation is the
-- instance boundary, never a query filter. [C-I]

-- ───────────────────────── enums ─────────────────────────

create type user_role as enum ('partner_manager', 'lawyer', 'paralegal', 'secretary');
create type user_status as enum ('active', 'inactive');
create type document_source_type as enum ('text_pdf', 'scanned');
create type document_status as enum ('pending', 'processing', 'ready', 'low_confidence', 'failed');
create type ai_output_type as enum ('summary', 'extraction', 'analysis', 'clause_flag', 'risk_signal');
create type review_state as enum ('draft_unreviewed', 'approved');
create type deadline_type as enum ('general', 'appeal_istinaf', 'mu_arada', 'naqd');
create type task_status as enum ('open', 'in_progress', 'done', 'cancelled');
create type notification_channel as enum ('whatsapp');
create type notification_status as enum ('sent', 'failed', 'skipped');
create type report_type as enum ('daily_what_happened', 'tomorrow_tasks');

-- ───────────────────────── firm_settings (singleton; holds secrets) ─────────────────────────

create table firm_settings (
    id                       uuid primary key default gen_random_uuid(),
    singleton                boolean not null default true unique check (singleton),
    firm_name                text not null default '',
    locale                   text not null default 'ar-EG',
    waha_url                 text,            -- secret-adjacent endpoint
    waha_key                 text,            -- SECRET: never logged as value [C-III]
    llm_api_key              text,            -- SECRET: client-provided [C-III]
    embedding_config         jsonb not null default '{"model": "", "dimension": 1536}'::jsonb,  -- R1
    reminder_lead_points     jsonb not null default '["7d", "3d", "1d", "0d"]'::jsonb,          -- R9
    feature_appeal_deadlines boolean not null default false,  -- [C-X] default OFF until expert sign-off
    subscription_metadata    jsonb not null default '{}'::jsonb,
    created_at               timestamptz not null default now(),
    updated_at               timestamptz not null default now()
);

-- ───────────────────────── users ─────────────────────────
-- Auth lives in GoTrue (auth.users); this row holds profile + role.
-- auth_user_id links to auth.users.id (no hard FK — GoTrue owns that schema).

create table users (
    id           uuid primary key default gen_random_uuid(),
    auth_user_id uuid unique,
    full_name    text not null,
    email        text not null unique,
    phone        text unique,                  -- verified phone; drives WhatsApp identity (R12)
    role         user_role not null,
    status       user_status not null default 'active',
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

-- ───────────────────────── cases (matters) ─────────────────────────

create table cases (
    id          uuid primary key default gen_random_uuid(),
    title       text not null,
    client_name text not null,
    case_number text,
    court       text,
    case_type   text,
    status      text not null default 'open',
    created_by  uuid references users (id),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- ───────────────────────── case_assignments (users ↔ cases) ─────────────────────────

create table case_assignments (
    id         uuid primary key default gen_random_uuid(),
    case_id    uuid not null references cases (id) on delete cascade,
    user_id    uuid not null references users (id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (case_id, user_id)
);

create index idx_case_assignments_user on case_assignments (user_id);
create index idx_case_assignments_case on case_assignments (case_id);

-- ───────────────────────── documents ─────────────────────────

create table documents (
    id             uuid primary key default gen_random_uuid(),
    case_id        uuid not null references cases (id) on delete cascade,
    file_path      text not null,               -- Supabase Storage object path
    file_name      text not null,
    source_type    document_source_type not null default 'scanned',
    status         document_status not null default 'pending',
    ocr_confidence real,                        -- raw mean confidence, gate input [C-VII]
    error_detail   text,                        -- surfaced to user on status=failed
    uploaded_by    uuid references users (id),
    uploaded_at    timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

create index idx_documents_case on documents (case_id);
create index idx_documents_status on documents (status);

-- ───────────────────────── document_chunks ─────────────────────────
-- chunk_text is normalized Arabic (R5); embedding indexed in 0003.

create table document_chunks (
    id              uuid primary key default gen_random_uuid(),
    document_id     uuid not null references documents (id) on delete cascade,
    chunk_index     int not null,
    chunk_text      text not null,
    embedding       vector(1536),               -- R1: dimension fixed per instance
    page_ref        int,                        -- grounding source location [C-V]
    source_location jsonb,                      -- richer locator (page, offsets) [C-V]
    created_at      timestamptz not null default now(),
    unique (document_id, chunk_index)
);

create index idx_document_chunks_document on document_chunks (document_id);

-- ───────────────────────── ai_outputs ─────────────────────────
-- Born draft_unreviewed; export/send requires approved. [C-II]
-- source_links ground every claim to chunks. [C-V]

create table ai_outputs (
    id                  uuid primary key default gen_random_uuid(),
    document_id         uuid references documents (id) on delete cascade,
    case_id             uuid references cases (id) on delete cascade,
    type                ai_output_type not null,
    content             jsonb not null,          -- structured content incl. claims
    source_links        jsonb not null default '[]'::jsonb,  -- [{chunk_id, document_id, page_ref}] [C-V]
    review_state        review_state not null default 'draft_unreviewed',  -- [C-II]
    low_confidence_flag boolean not null default false,       -- propagated from source doc [C-VII]
    generated_by_model  text,
    created_at          timestamptz not null default now(),
    approved_by         uuid references users (id),
    approved_at         timestamptz,
    approved_version    int,
    check (document_id is not null or case_id is not null),
    -- approval fields are all-or-nothing with the state [C-II]
    check (
        (review_state = 'draft_unreviewed' and approved_by is null and approved_at is null)
        or
        (review_state = 'approved' and approved_by is not null and approved_at is not null)
    )
);

create index idx_ai_outputs_review_state on ai_outputs (review_state);
create index idx_ai_outputs_document on ai_outputs (document_id);
create index idx_ai_outputs_case on ai_outputs (case_id);

-- ───────────────────────── deadlines ─────────────────────────
-- Appeal types are suggestions: confirmed=false, inert until verified. [C-X]

create table deadlines (
    id                       uuid primary key default gen_random_uuid(),
    case_id                  uuid not null references cases (id) on delete cascade,
    type                     deadline_type not null default 'general',
    title                    text not null,
    basis                    text,               -- legal basis for appeal suggestions [C-X]
    due_date                 date not null,
    suggested_date           date,
    confirmed                boolean not null default false,
    confirmed_by             uuid references users (id),
    confirmed_at             timestamptz,
    responsible_user_id      uuid not null references users (id),
    derived_from_document_id uuid references documents (id),
    low_confidence_flag      boolean not null default false,  -- [C-VII]
    acknowledged_at          timestamptz,        -- drives partner escalation (R9)
    created_at               timestamptz not null default now(),
    updated_at               timestamptz not null default now()
);

create index idx_deadlines_case on deadlines (case_id);
create index idx_deadlines_due on deadlines (due_date) where confirmed;
create index idx_deadlines_responsible on deadlines (responsible_user_id);

-- ───────────────────────── tasks ─────────────────────────

create table tasks (
    id          uuid primary key default gen_random_uuid(),
    case_id     uuid not null references cases (id) on delete cascade,
    assigned_to uuid not null references users (id),
    description text not null,
    due_date    date,
    status      task_status not null default 'open',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index idx_tasks_case on tasks (case_id);
create index idx_tasks_assigned on tasks (assigned_to);
create index idx_tasks_due on tasks (due_date);

-- ───────────────────────── notifications_log ─────────────────────────
-- One row per send ATTEMPT, incl. failed/skipped — never silently dropped (FR-025).

create table notifications_log (
    id                uuid primary key default gen_random_uuid(),
    deadline_id       uuid references deadlines (id) on delete set null,
    task_id           uuid references tasks (id) on delete set null,
    recipient_user_id uuid not null references users (id),
    channel           notification_channel not null default 'whatsapp',
    lead_point        text,                      -- which configured lead point fired (e.g. '3d')
    is_escalation     boolean not null default false,  -- partner escalation send (R9)
    scheduled_for     timestamptz not null,
    sent_at           timestamptz,
    status            notification_status not null,
    error_detail      text,
    created_at        timestamptz not null default now(),
    check (deadline_id is not null or task_id is not null)
);

create index idx_notifications_deadline on notifications_log (deadline_id);
create index idx_notifications_recipient on notifications_log (recipient_user_id);

-- ───────────────────────── reports_log ─────────────────────────

create table reports_log (
    id                uuid primary key default gen_random_uuid(),
    type              report_type not null,
    recipient_user_id uuid not null references users (id),
    content           text,                      -- the phrased prose actually sent
    items             jsonb not null default '[]'::jsonb,  -- code-selected facts (reconcile to audit) [C-IV]
    generated_at      timestamptz not null default now(),
    sent_at           timestamptz
);

-- ───────────────────────── references_private ─────────────────────────
-- Firm's own reference uploads; chunked+embedded like documents (private corpus).

create table references_private (
    id          uuid primary key default gen_random_uuid(),
    title       text not null,
    file_path   text not null,
    status      document_status not null default 'pending',
    uploaded_by uuid references users (id),
    uploaded_at timestamptz not null default now()
);

create table reference_chunks (
    id              uuid primary key default gen_random_uuid(),
    reference_id    uuid not null references references_private (id) on delete cascade,
    chunk_index     int not null,
    chunk_text      text not null,
    embedding       vector(1536),
    page_ref        int,
    source_location jsonb,
    created_at      timestamptz not null default now(),
    unique (reference_id, chunk_index)
);

create index idx_reference_chunks_reference on reference_chunks (reference_id);

-- NOTE: the shared Egyptian-law corpus is NOT in this schema. It is a separate,
-- central, read-only database (public law only — no firm data ever). [C-I]

-- ───────────────────────── updated_at maintenance ─────────────────────────

create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

do $$
declare
    t text;
begin
    foreach t in array array['firm_settings', 'users', 'cases', 'documents', 'deadlines', 'tasks']
    loop
        execute format(
            'create trigger trg_%s_updated_at before update on %I
             for each row execute function set_updated_at()', t, t);
    end loop;
end
$$;

-- ───────────────────────── grants ─────────────────────────
-- app_user gets table access; RLS (0007) constrains rows by in-instance role.

grant select, insert, update, delete on all tables in schema public to app_user;
grant usage on all sequences in schema public to app_user;
