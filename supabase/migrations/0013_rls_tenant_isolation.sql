-- 0013_rls_tenant_isolation.sql
-- SaaS conversion (WP-S1): cross-firm isolation in SQL. [C-I v2]
-- Fail-closed: with app.firm_id unset, rls_same_firm() is NULL ⇒ zero rows.
-- Every policy from 0007 is recreated with the firm predicate ANDed in front.

create or replace function rls_current_firm_id()
returns uuid language sql stable
set search_path = public, pg_temp as $$
    select nullif(current_setting('app.firm_id', true), '')::uuid;
$$;

create or replace function rls_same_firm(p_firm uuid)
returns boolean language sql stable
set search_path = public, pg_temp as $$
    select p_firm = rls_current_firm_id();   -- NULL ⇒ false ⇒ fail closed
$$;

-- SECURITY DEFINER bypasses RLS ⇒ the firm check must be explicit inside.
create or replace function rls_assigned_to_case(p_case_id uuid)
returns boolean language sql stable security definer
set search_path = public, pg_temp as $$
    select exists (
        select 1 from case_assignments
        where case_id = p_case_id
          and user_id = rls_current_user_id()
          and firm_id = rls_current_firm_id()
    );
$$;

-- ── firms / subscriptions / billing_events ────────────────────────────────────
alter table firms enable row level security;
create policy firms_select_own on firms
    for select to app_user using (rls_same_firm(id));

alter table subscriptions enable row level security;
create policy subscriptions_select_own on subscriptions
    for select to app_user using (rls_same_firm(firm_id) and rls_is_manager());

alter table billing_events enable row level security;
-- no app_user policies: service-context only.

-- ── drop all 0007 policies, recreate with firm predicate ──────────────────────

-- firm_settings
drop policy if exists firm_settings_manager_all on firm_settings;
create policy firm_settings_manager_all on firm_settings
    for all to app_user
    using (rls_same_firm(firm_id) and rls_is_manager())
    with check (rls_same_firm(firm_id) and rls_is_manager());

-- the non-secret settings view: invoker security + firm filter (cloud-safe)
drop view if exists firm_public_settings;
create view firm_public_settings
    with (security_invoker = true) as
    select id, firm_id, firm_name, locale, reminder_lead_points, feature_appeal_deadlines
    from firm_settings
    where rls_same_firm(firm_id);
grant select on firm_public_settings to app_user;

-- users
drop policy if exists users_select_all on users;
drop policy if exists users_manager_write on users;
drop policy if exists users_manager_update on users;
drop policy if exists users_manager_delete on users;
create policy users_select_same_firm on users
    for select to app_user using (rls_same_firm(firm_id));
create policy users_manager_write on users
    for insert to app_user with check (rls_same_firm(firm_id) and rls_is_manager());
create policy users_manager_update on users
    for update to app_user
    using (rls_same_firm(firm_id) and rls_is_manager())
    with check (rls_same_firm(firm_id) and rls_is_manager());
create policy users_manager_delete on users
    for delete to app_user using (rls_same_firm(firm_id) and rls_is_manager());

-- cases
drop policy if exists cases_select on cases;
drop policy if exists cases_insert on cases;
drop policy if exists cases_update on cases;
drop policy if exists cases_delete on cases;
create policy cases_select on cases
    for select to app_user
    using (rls_same_firm(firm_id) and (rls_is_manager() or rls_assigned_to_case(id)));
create policy cases_insert on cases
    for insert to app_user
    with check (rls_same_firm(firm_id) and rls_current_role() in ('partner_manager','lawyer'));
create policy cases_update on cases
    for update to app_user
    using (rls_same_firm(firm_id) and
           (rls_is_manager() or (rls_current_role() = 'lawyer' and rls_assigned_to_case(id))));
create policy cases_delete on cases
    for delete to app_user
    using (rls_same_firm(firm_id) and rls_is_manager());

-- case_assignments
drop policy if exists case_assignments_select on case_assignments;
drop policy if exists case_assignments_write on case_assignments;
drop policy if exists case_assignments_delete on case_assignments;
create policy case_assignments_select on case_assignments
    for select to app_user
    using (rls_same_firm(firm_id) and
           (rls_is_manager() or rls_assigned_to_case(case_id) or user_id = rls_current_user_id()));
create policy case_assignments_write on case_assignments
    for insert to app_user
    with check (rls_same_firm(firm_id) and rls_current_role() in ('partner_manager','lawyer'));
create policy case_assignments_delete on case_assignments
    for delete to app_user
    using (rls_same_firm(firm_id) and rls_current_role() in ('partner_manager','lawyer'));

-- documents
drop policy if exists documents_select on documents;
drop policy if exists documents_insert on documents;
drop policy if exists documents_update on documents;
drop policy if exists documents_delete on documents;
create policy documents_select on documents
    for select to app_user
    using (rls_same_firm(firm_id) and (rls_is_manager() or rls_assigned_to_case(case_id)));
create policy documents_insert on documents
    for insert to app_user
    with check (rls_same_firm(firm_id) and (rls_is_manager() or rls_assigned_to_case(case_id)));
create policy documents_update on documents
    for update to app_user
    using (rls_same_firm(firm_id) and (rls_is_manager() or rls_assigned_to_case(case_id)));
create policy documents_delete on documents
    for delete to app_user
    using (rls_same_firm(firm_id) and rls_is_manager());

-- document_chunks — the RAG isolation line. [C-I]
drop policy if exists document_chunks_select on document_chunks;
create policy document_chunks_select on document_chunks
    for select to app_user
    using (
        rls_same_firm(firm_id)
        and (rls_is_manager() or exists (
            select 1 from documents d
            where d.id = document_id and rls_assigned_to_case(d.case_id)
        ))
    );

-- ai_outputs
drop policy if exists ai_outputs_select on ai_outputs;
drop policy if exists ai_outputs_insert on ai_outputs;
drop policy if exists ai_outputs_update on ai_outputs;
drop policy if exists ai_outputs_delete on ai_outputs;
create policy ai_outputs_select on ai_outputs
    for select to app_user
    using (
        rls_same_firm(firm_id) and (
            rls_is_manager()
            or (case_id is not null and rls_assigned_to_case(case_id))
            or (document_id is not null and exists (
                    select 1 from documents d
                    where d.id = document_id and rls_assigned_to_case(d.case_id)))
        )
    );
create policy ai_outputs_insert on ai_outputs
    for insert to app_user
    with check (
        rls_same_firm(firm_id) and (
            rls_is_manager()
            or (case_id is not null and rls_assigned_to_case(case_id))
            or (document_id is not null and exists (
                    select 1 from documents d
                    where d.id = document_id and rls_assigned_to_case(d.case_id)))
        )
    );
create policy ai_outputs_update on ai_outputs
    for update to app_user
    using (
        rls_same_firm(firm_id) and (
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
        )
    );
create policy ai_outputs_delete on ai_outputs
    for delete to app_user
    using (rls_same_firm(firm_id) and rls_is_manager());

-- export view follows invoker (firm + role policies apply through it)
drop view if exists ai_outputs_exportable;
create view ai_outputs_exportable
    with (security_invoker = true) as
    select * from ai_outputs where review_state = 'approved';
grant select on ai_outputs_exportable to app_user;
comment on view ai_outputs_exportable is
    'The ONLY read path for export/print/attach/official-send. review_state = approved; RLS of invoker applies. [C-II]';

-- deadlines
drop policy if exists deadlines_select on deadlines;
drop policy if exists deadlines_write on deadlines;
drop policy if exists deadlines_update on deadlines;
drop policy if exists deadlines_delete on deadlines;
create policy deadlines_select on deadlines
    for select to app_user
    using (rls_same_firm(firm_id) and (rls_is_manager() or rls_assigned_to_case(case_id)));
create policy deadlines_write on deadlines
    for insert to app_user
    with check (rls_same_firm(firm_id) and
                (rls_is_manager() or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id))));
create policy deadlines_update on deadlines
    for update to app_user
    using (rls_same_firm(firm_id) and
           (rls_is_manager() or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id))));
create policy deadlines_delete on deadlines
    for delete to app_user
    using (rls_same_firm(firm_id) and
           (rls_is_manager() or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id))));

-- tasks
drop policy if exists tasks_select on tasks;
drop policy if exists tasks_insert on tasks;
drop policy if exists tasks_update on tasks;
drop policy if exists tasks_delete on tasks;
create policy tasks_select on tasks
    for select to app_user
    using (rls_same_firm(firm_id) and
           (rls_is_manager() or rls_assigned_to_case(case_id) or assigned_to = rls_current_user_id()));
create policy tasks_insert on tasks
    for insert to app_user
    with check (rls_same_firm(firm_id)
        and rls_current_role() in ('partner_manager','lawyer','paralegal')
        and (rls_is_manager() or rls_assigned_to_case(case_id)));
create policy tasks_update on tasks
    for update to app_user
    using (rls_same_firm(firm_id) and
           (rls_is_manager() or assigned_to = rls_current_user_id()
            or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id))));
create policy tasks_delete on tasks
    for delete to app_user
    using (rls_same_firm(firm_id) and
           (rls_is_manager() or (rls_current_role() = 'lawyer' and rls_assigned_to_case(case_id))));

-- notifications_log / reports_log
drop policy if exists notifications_select on notifications_log;
create policy notifications_select on notifications_log
    for select to app_user
    using (rls_same_firm(firm_id) and
           (rls_is_manager() or recipient_user_id = rls_current_user_id()));

drop policy if exists reports_select on reports_log;
create policy reports_select on reports_log
    for select to app_user
    using (rls_same_firm(firm_id) and rls_is_manager());

-- references_private / reference_chunks (firm-internal corpus)
drop policy if exists references_select on references_private;
drop policy if exists references_insert on references_private;
drop policy if exists references_delete on references_private;
create policy references_select on references_private
    for select to app_user using (rls_same_firm(firm_id));
create policy references_insert on references_private
    for insert to app_user
    with check (rls_same_firm(firm_id) and
                rls_current_role() in ('partner_manager','lawyer','paralegal'));
create policy references_delete on references_private
    for delete to app_user
    using (rls_same_firm(firm_id) and rls_is_manager());

drop policy if exists reference_chunks_select on reference_chunks;
create policy reference_chunks_select on reference_chunks
    for select to app_user using (rls_same_firm(firm_id));

-- audit_log: manager reads own firm's entries only
drop policy if exists audit_log_manager_select on audit_log;
create policy audit_log_manager_select on audit_log
    for select to app_user
    using (rls_same_firm(firm_id) and rls_is_manager());

-- NOTE: the shared Egyptian-law corpus tables (when added) get NO firm_id and
-- a plain read-only policy — public law only, global by design. [C-I hard line]
