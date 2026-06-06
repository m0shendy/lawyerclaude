-- 0007_rls_roles.sql
-- RLS for IN-INSTANCE roles only (partner_manager / lawyer / paralegal /
-- secretary). This is NOT the cross-firm boundary — that is the instance
-- (separate stack/DB) [C-I]. The backend connects as app_user and sets
-- app.user_id / app.user_role GUCs per request (see core/db.py).

-- Helper predicates -----------------------------------------------------------

create or replace function rls_current_user_id()
returns uuid language sql stable as $$
    select nullif(current_setting('app.user_id', true), '')::uuid;
$$;

create or replace function rls_current_role()
returns text language sql stable as $$
    select nullif(current_setting('app.user_role', true), '');
$$;

create or replace function rls_is_manager()
returns boolean language sql stable as $$
    select rls_current_role() = 'partner_manager';
$$;

create or replace function rls_assigned_to_case(p_case_id uuid)
returns boolean language sql stable security definer as $$
    select exists (
        select 1 from case_assignments
        where case_id = p_case_id and user_id = rls_current_user_id()
    );
$$;

-- firm_settings: manager-only (secrets live here) -------------------------------

alter table firm_settings enable row level security;

create policy firm_settings_manager_all on firm_settings
    for all to app_user
    using (rls_is_manager())
    with check (rls_is_manager());

-- A narrow non-secret read path for all roles (locale, flags) is provided via a view.
create or replace view firm_public_settings
    with (security_invoker = false) as
    select id, firm_name, locale, reminder_lead_points, feature_appeal_deadlines
    from firm_settings;
grant select on firm_public_settings to app_user;

-- users: everyone reads (names needed for assignment UI); only manager mutates ---

alter table users enable row level security;

create policy users_select_all on users
    for select to app_user using (true);

create policy users_manager_write on users
    for insert to app_user with check (rls_is_manager());
create policy users_manager_update on users
    for update to app_user using (rls_is_manager()) with check (rls_is_manager());
create policy users_manager_delete on users
    for delete to app_user using (rls_is_manager());

-- cases: manager sees all; others see assigned cases ----------------------------

alter table cases enable row level security;

create policy cases_select on cases
    for select to app_user
    using (rls_is_manager() or rls_assigned_to_case(id));

create policy cases_insert on cases
    for insert to app_user
    with check (rls_current_role() in ('partner_manager', 'lawyer'));

create policy cases_update on cases
    for update to app_user
    using (rls_is_manager() or (rls_current_role() = 'lawyer' and rls_assigned_to_case(id)));

create policy cases_delete on cases
    for delete to app_user
    using (rls_is_manager());

-- case_assignments --------------------------------------------------------------

alter table case_assignments enable row level security;

create policy case_assignments_select on case_assignments
    for select to app_user
    using (rls_is_manager() or rls_assigned_to_case(case_id) or user_id = rls_current_user_id());

create policy case_assignments_write on case_assignments
    for insert to app_user
    with check (rls_current_role() in ('partner_manager', 'lawyer'));

create policy case_assignments_delete on case_assignments
    for delete to app_user
    using (rls_current_role() in ('partner_manager', 'lawyer'));

-- documents: scoped to assigned cases; all roles may upload ----------------------

alter table documents enable row level security;

create policy documents_select on documents
    for select to app_user
    using (rls_is_manager() or rls_assigned_to_case(case_id));

create policy documents_insert on documents
    for insert to app_user
    with check (rls_is_manager() or rls_assigned_to_case(case_id));

create policy documents_update on documents
    for update to app_user
    using (rls_is_manager() or rls_assigned_to_case(case_id));

create policy documents_delete on documents
    for delete to app_user
    using (rls_is_manager());

-- document_chunks: read follows the parent document ------------------------------

alter table document_chunks enable row level security;

create policy document_chunks_select on document_chunks
    for select to app_user
    using (
        rls_is_manager() or exists (
            select 1 from documents d
            where d.id = document_id and rls_assigned_to_case(d.case_id)
        )
    );
-- Chunk writes happen via the pipeline worker (service context, no user GUC) —
-- the worker connects with a connection that bypasses via service_role, or as
-- app_user with explicit policy below for system writes (user id null + role null
-- never matches; workers use the service path). No app_user write policy.

-- ai_outputs ---------------------------------------------------------------------

alter table ai_outputs enable row level security;

create policy ai_outputs_select on ai_outputs
    for select to app_user
    using (
        rls_is_manager()
        or (case_id is not null and rls_assigned_to_case(case_id))
        or (document_id is not null and exists (
                select 1 from documents d
                where d.id = document_id and rls_assigned_to_case(d.case_id)))
    );

create policy ai_outputs_insert on ai_outputs
    for insert to app_user
    with check (
        rls_is_manager()
        or (case_id is not null and rls_assigned_to_case(case_id))
        or (document_id is not null and exists (
                select 1 from documents d
                where d.id = document_id and rls_assigned_to_case(d.case_id)))
    );

-- Approval (the only meaningful update) is restricted to assigned LAWYER or
-- manager — paralegal/secretary cannot approve even on their own cases (FR-018).
create policy ai_outputs_update on ai_outputs
    for update to app_user
    using (
        rls_is_manager()
        or (
            rls_current_role() = 'lawyer'
            and (
                (case_id is not null and rls_assigned_to_case(case_id))
                or (document_id is not null and exists (
                        select 1 from documents d
                        where d.id = document_id and rls_assigned_to_case(d.case_id)))
            )
        )
    );

create policy ai_outputs_delete on ai_outputs
    for delete to app_user
    using (rls_is_manager());

-- deadlines ----------------------------------------------------------------------

alter table deadlines enable row level security;

create policy deadlines_select on deadlines
    for select to app_user
    using (rls_is_manager() or rls_assigned_to_case(case_id));

create policy deadlines_write on deadlines
    for insert to app_user
    with check (
        rls_is_manager()
        or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id))
    );

create policy deadlines_update on deadlines
    for update to app_user
    using (
        rls_is_manager()
        or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id))
    );

create policy deadlines_delete on deadlines
    for delete to app_user
    using (
        rls_is_manager()
        or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id))
    );

-- tasks --------------------------------------------------------------------------

alter table tasks enable row level security;

create policy tasks_select on tasks
    for select to app_user
    using (rls_is_manager() or rls_assigned_to_case(case_id) or assigned_to = rls_current_user_id());

create policy tasks_insert on tasks
    for insert to app_user
    with check (
        rls_current_role() in ('partner_manager', 'lawyer', 'paralegal')
        and (rls_is_manager() or rls_assigned_to_case(case_id))
    );

create policy tasks_update on tasks
    for update to app_user
    using (rls_is_manager() or assigned_to = rls_current_user_id()
           or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id)));

create policy tasks_delete on tasks
    for delete to app_user
    using (rls_is_manager() or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id)));

-- notifications_log / reports_log: written by the deterministic scheduler
-- (service context). Managers may read; reports recipients read their own. ------

alter table notifications_log enable row level security;

create policy notifications_select on notifications_log
    for select to app_user
    using (rls_is_manager() or recipient_user_id = rls_current_user_id());

alter table reports_log enable row level security;

create policy reports_select on reports_log
    for select to app_user
    using (rls_is_manager());

-- references_private / reference_chunks: firm-internal references ----------------

alter table references_private enable row level security;

create policy references_select on references_private
    for select to app_user using (true);

create policy references_insert on references_private
    for insert to app_user
    with check (rls_current_role() in ('partner_manager', 'lawyer', 'paralegal'));

create policy references_delete on references_private
    for delete to app_user using (rls_is_manager());

alter table reference_chunks enable row level security;

create policy reference_chunks_select on reference_chunks
    for select to app_user using (true);
