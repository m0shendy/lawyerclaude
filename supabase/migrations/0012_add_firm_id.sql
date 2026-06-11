-- 0012_add_firm_id.sql
-- SaaS conversion (WP-S1): every tenant table carries firm_id. Existing rows
-- backfill to a Default Firm so the migration is safe on a populated instance.

-- 0) Default firm for backfill.
insert into firms (name, slug, status)
values ('Default Firm', 'default', 'active')
on conflict (slug) do nothing;

-- 1) Add firm_id (nullable → backfill → not null) on all tenant tables.
do $$
declare
    t text;
    v_default uuid;
begin
    select id into v_default from firms where slug = 'default';
    foreach t in array array[
        'firm_settings','users','cases','case_assignments','documents',
        'document_chunks','ai_outputs','deadlines','tasks',
        'notifications_log','reports_log','references_private','reference_chunks'
    ] loop
        execute format('alter table %I add column if not exists firm_id uuid references firms(id)', t);
        execute format('update %I set firm_id = $1 where firm_id is null', t) using v_default;
        execute format('alter table %I alter column firm_id set not null', t);
    end loop;
end $$;

-- 2) firm_settings: one row per firm (replaces the singleton).
alter table firm_settings drop constraint if exists firm_settings_singleton_key;
alter table firm_settings drop column if exists singleton;
alter table firm_settings add constraint firm_settings_one_per_firm unique (firm_id);

-- 3) Tenant-aware uniqueness: emails/phones are unique per firm, not globally.
alter table users drop constraint if exists users_email_key;
alter table users drop constraint if exists users_phone_key;
alter table users add constraint users_email_per_firm unique (firm_id, email);
alter table users add constraint users_phone_per_firm unique (firm_id, phone);

-- 4) Hot-path composite indexes.
create index if not exists idx_users_firm              on users (firm_id);
create index if not exists idx_cases_firm              on cases (firm_id);
create index if not exists idx_documents_firm_case     on documents (firm_id, case_id);
create index if not exists idx_chunks_firm_document    on document_chunks (firm_id, document_id);
create index if not exists idx_ai_outputs_firm_state   on ai_outputs (firm_id, review_state);
create index if not exists idx_deadlines_firm_due      on deadlines (firm_id, due_date);
create index if not exists idx_tasks_firm_assignee     on tasks (firm_id, assigned_to);
create index if not exists idx_refchunks_firm          on reference_chunks (firm_id);

-- 5) audit_log gains firm context (nullable: platform-level events have none).
alter table audit_log add column if not exists firm_id uuid;
create index if not exists idx_audit_log_firm on audit_log (firm_id);

-- 6) Audit trigger records firm_id: from the row when present, else from the GUC.
create or replace function audit_trigger()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
declare
    v_user_id uuid;
    v_role    text;
    v_context text;
    v_firm    uuid;
    v_record  uuid;
    v_diff    jsonb;
    v_action  audit_action;
    old_j     jsonb;
    new_j     jsonb;
    k         text;
begin
    begin
        v_user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    exception when others then
        v_user_id := null;
    end;
    v_role    := nullif(current_setting('app.user_role', true), '');
    v_context := nullif(current_setting('app.context', true), '');
    begin
        v_firm := nullif(current_setting('app.firm_id', true), '')::uuid;
    exception when others then
        v_firm := null;
    end;

    if tg_op = 'INSERT' then
        v_action := 'create';
        new_j := to_jsonb(new);
        v_record := (new_j ->> 'id')::uuid;
        v_firm := coalesce((new_j ->> 'firm_id')::uuid, v_firm);
        v_diff := (
            select coalesce(jsonb_object_agg(key, jsonb_build_object('old', null, 'new', value)), '{}'::jsonb)
            from jsonb_each(new_j)
            where value is not null and value != 'null'::jsonb
        );
    elsif tg_op = 'UPDATE' then
        v_action := 'update';
        old_j := to_jsonb(old);
        new_j := to_jsonb(new);
        v_record := (new_j ->> 'id')::uuid;
        v_firm := coalesce((new_j ->> 'firm_id')::uuid, v_firm);
        v_diff := '{}'::jsonb;
        for k in select jsonb_object_keys(new_j) loop
            if (old_j -> k) is distinct from (new_j -> k) then
                v_diff := v_diff || jsonb_build_object(
                    k, jsonb_build_object('old', old_j -> k, 'new', new_j -> k));
            end if;
        end loop;
        if v_diff = '{}'::jsonb then
            return new;
        end if;
    else
        v_action := 'delete';
        old_j := to_jsonb(old);
        v_record := (old_j ->> 'id')::uuid;
        v_firm := coalesce((old_j ->> 'firm_id')::uuid, v_firm);
        v_diff := (
            select coalesce(jsonb_object_agg(key, jsonb_build_object('old', value, 'new', null)), '{}'::jsonb)
            from jsonb_each(old_j)
        );
    end if;

    v_diff := audit_redact_secrets(tg_table_name, v_diff);

    insert into audit_log (who_user_id, who_role, entity_table, record_id, action, change_detail, context, firm_id)
    values (v_user_id, v_role, tg_table_name, v_record, v_action, v_diff, v_context, v_firm);

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;
