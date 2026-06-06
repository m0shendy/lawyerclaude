-- 0016_add_hearings.sql
-- Module C: Court Hearings (الجلسات)
-- Tracks scheduled court sessions, outcomes, and next hearing dates.
-- Integrates with the existing deadline reminder scheduler pattern.

create type hearing_status as enum ('scheduled', 'held', 'adjourned', 'cancelled');

create table hearings (
    id                   uuid           primary key default gen_random_uuid(),
    case_id              uuid           not null references cases(id) on delete cascade,
    hearing_date         timestamptz    not null,
    court_name           text           not null,    -- اسم المحكمة
    court_room           text,                       -- قاعة / دائرة
    judge_contact_id     uuid           references contacts(id),
    assigned_lawyer_id   uuid           references users(id),
    status               hearing_status not null default 'scheduled',
    -- Outcome (filled after session)
    result               text,                       -- نتيجة الجلسة
    next_hearing_date    timestamptz,
    next_hearing_court   text,
    notes                text,
    -- Reminder tracking (mirrors deadlines pattern)
    reminder_sent_7d     boolean        not null default false,
    reminder_sent_3d     boolean        not null default false,
    reminder_sent_1d     boolean        not null default false,
    reminder_sent_0d     boolean        not null default false,
    created_by           uuid           references users(id),
    created_at           timestamptz    not null default now(),
    updated_at           timestamptz    not null default now()
);

create index idx_hearings_case        on hearings (case_id);
create index idx_hearings_date        on hearings (hearing_date) where status = 'scheduled';
create index idx_hearings_lawyer      on hearings (assigned_lawyer_id);
create index idx_hearings_upcoming    on hearings (hearing_date)
    where status = 'scheduled' and hearing_date > now();

-- ── RLS ──────────────────────────────────────────────────────────────────────

alter table hearings enable row level security;

create policy hearings_manager on hearings
    for all to app_user using (rls_is_manager()) with check (rls_is_manager());

create policy hearings_assigned_select on hearings
    for select to app_user using (rls_assigned_to_case(case_id));

create policy hearings_assigned_write on hearings
    for all to app_user
    using (rls_assigned_to_case(case_id) and rls_current_role() in ('lawyer','paralegal','secretary'))
    with check (rls_assigned_to_case(case_id) and rls_current_role() in ('lawyer','paralegal','secretary'));

-- ── audit trigger ─────────────────────────────────────────────────────────────
select attach_audit_trigger('hearings');
