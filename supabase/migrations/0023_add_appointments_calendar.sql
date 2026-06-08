-- 0023_add_appointments_calendar.sql
-- Spec 002 gap closure (part 3 of 3): Appointments (US7) + unified calendar (US8).
-- Appointment conflict detection runs at the API layer via tstzrange overlap;
-- a GiST exclusion constraint backstops it at the DB level.

create extension if not exists btree_gist;

create type appointment_type as enum ('consultation', 'follow_up', 'checkup', 'emergency');
create type appointment_status as enum
    ('scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled');

create table appointments (
    id                 uuid               primary key default gen_random_uuid(),
    type               appointment_type   not null default 'consultation',
    case_id            uuid               references cases(id) on delete set null,
    contact_id         uuid               references contacts(id) on delete set null,
    assigned_lawyer_id uuid               not null references users(id),
    scheduled_at       timestamptz        not null,
    duration_minutes   integer            not null default 60 check (duration_minutes > 0),
    status             appointment_status not null default 'scheduled',
    reason             text,
    notes              text,
    created_by         uuid               references users(id),
    created_at         timestamptz        not null default now(),
    updated_at         timestamptz        not null default now()
    -- Note: double-booking guard runs at the API layer via tstzrange overlap
    -- query (FR-129). A GiST exclusion constraint on timestamptz expressions
    -- requires IMMUTABLE functions which PostgreSQL does not allow here.
);

create index idx_appointments_case    on appointments (case_id);
create index idx_appointments_contact on appointments (contact_id);
create index idx_appointments_lawyer  on appointments (assigned_lawyer_id, scheduled_at);
create index idx_appointments_date    on appointments (scheduled_at)
    where status not in ('cancelled', 'completed');

-- ── RLS (mirrors hearings posture) ───────────────────────────────────────────

alter table appointments enable row level security;

create policy appointments_manager on appointments
    for all to app_user using (rls_is_manager()) with check (rls_is_manager());

create policy appointments_staff_select on appointments
    for select to app_user using (
        assigned_lawyer_id = rls_current_user_id()
        or created_by = rls_current_user_id()
        or (case_id is not null and rls_assigned_to_case(case_id)));

create policy appointments_staff_write on appointments
    for all to app_user
    using (rls_current_role() in ('lawyer', 'paralegal', 'secretary')
           and (assigned_lawyer_id = rls_current_user_id()
                or created_by = rls_current_user_id()
                or (case_id is not null and rls_assigned_to_case(case_id))))
    with check (rls_current_role() in ('lawyer', 'paralegal', 'secretary'));

select attach_audit_trigger('appointments');

-- ── calendar_events: unified view over hearings + appointments (R7, US8) ────

create view calendar_events as
    select h.id,
           'hearing'::text          as event_type,
           coalesce(h.court_name, 'جلسة') as title,
           h.hearing_date           as starts_at,
           h.hearing_date + interval '2 hours' as ends_at,
           h.case_id,
           h.assigned_lawyer_id,
           h.status::text           as status
    from hearings h
    union all
    select a.id,
           'appointment'::text      as event_type,
           coalesce(a.reason, a.type::text) as title,
           a.scheduled_at           as starts_at,
           a.scheduled_at + a.duration_minutes * interval '1 minute' as ends_at,
           a.case_id,
           a.assigned_lawyer_id,
           a.status::text           as status
    from appointments a;

-- View runs with the invoker's rights so hearings/appointments RLS applies.
alter view calendar_events set (security_invoker = true);
