-- 0021_expansion_gaps.sql
-- Spec 002 gap closure (part 1 of 3): matter extensions, task priority,
-- conflict-check log, ai_output_type additions, firm_settings LLM provider
-- config. Adapts spec 002 tasks T006/T007/T010/T014/T015/T087 onto the
-- existing schema (contacts module = client registry; no separate clients
-- table).

-- ── cases: extended matter fields (FR-108..FR-111) ──────────────────────────

create sequence if not exists cases_number_seq start 1;

alter table cases
    add column if not exists practice_area    text,
    add column if not exists jurisdiction     text,
    add column if not exists opposing_counsel text,
    add column if not exists docket_number    text,
    add column if not exists tags             text[] not null default '{}',
    add column if not exists priority         text not null default 'medium'
        check (priority in ('low', 'medium', 'high')),
    add column if not exists stage            text not null default 'intake'
        check (stage in ('intake', 'active', 'litigation', 'settlement', 'closed'));

-- Auto-number new matters that arrive without an explicit case_number.
-- Existing rows (and user-supplied court numbers) are left untouched.
create or replace function cases_autonumber()
returns trigger language plpgsql as $$
begin
    if new.case_number is null or new.case_number = '' then
        new.case_number := 'CASE-' || lpad(nextval('cases_number_seq')::text, 4, '0');
    end if;
    return new;
end; $$;

drop trigger if exists trg_cases_autonumber on cases;
create trigger trg_cases_autonumber
    before insert on cases
    for each row execute function cases_autonumber();

-- Full-text index over opposing counsel for the conflict check (R5).
alter table cases
    add column if not exists opposing_counsel_tsvec tsvector
        generated always as (to_tsvector('arabic', coalesce(opposing_counsel, ''))) stored;

create index if not exists idx_cases_opposing_tsvec
    on cases using gin (opposing_counsel_tsvec);

create index if not exists idx_cases_stage_priority on cases (stage, priority);

-- ── tasks: priority level (FR-142) ──────────────────────────────────────────

alter table tasks
    add column if not exists priority text not null default 'medium'
        check (priority in ('low', 'medium', 'high'));

create index if not exists idx_tasks_priority_status on tasks (priority, status);

-- ── conflict_check_log (FR-110) ──────────────────────────────────────────────

create table if not exists conflict_check_log (
    id                 uuid        primary key default gen_random_uuid(),
    checked_by         uuid        references users(id),
    checked_at         timestamptz not null default now(),
    new_party_name     text        not null,
    matched_case_id    uuid        references cases(id) on delete set null,
    matched_contact_id uuid        references contacts(id) on delete set null,
    matched_party_name text,
    result             text        not null check (result in ('clear', 'conflict_found'))
);

create index if not exists idx_conflict_log_checked_at on conflict_check_log (checked_at desc);

alter table conflict_check_log enable row level security;

-- Any staff member may run / read conflict checks; clients have no app_user role.
create policy conflict_log_select on conflict_check_log
    for select to app_user using (true);

create policy conflict_log_insert on conflict_check_log
    for insert to app_user with check (true);

select attach_audit_trigger('conflict_check_log');

-- ── ai_outputs: new output types (US1/US12/US13) ─────────────────────────────

alter type ai_output_type add value if not exists 'doc_draft';
alter type ai_output_type add value if not exists 'letter_pack';
alter type ai_output_type add value if not exists 'case_timeline';

alter table ai_outputs
    add column if not exists template_id uuid references document_templates(id) on delete set null;

-- ── firm_settings: multi-provider LLM + DMS checkout timeout (FR-141, R1) ────

alter table firm_settings
    add column if not exists llm_provider_config jsonb not null default
        '{"provider": "gemini", "model": "models/gemini-2.0-flash"}'::jsonb,
    add column if not exists checkout_timeout_hours integer not null default 24
        check (checkout_timeout_hours > 0);

comment on column firm_settings.llm_provider_config is
    'Per-firm LiteLLM dispatch config {provider, model}. The API key stays in '
    'llm_api_key (secret column, action-only audit logging) [C-III].';
