-- 0005_audit_triggers.sql
-- Generic audit trigger attached to every audited table. [C-III]
-- Captures the acting user/role/context from per-connection GUCs set by the
-- backend (app.user_id / app.user_role / app.context); computes a field-level
-- old→new diff; REDACTS secret columns (logged as changed, never the value).

create or replace function audit_redact_secrets(tbl text, diff jsonb)
returns jsonb language plpgsql immutable as $$
declare
    secret_cols text[] := case
        when tbl = 'firm_settings' then array['waha_key', 'llm_api_key']
        else array[]::text[]
    end;
    col text;
begin
    foreach col in array secret_cols loop
        if diff ? col then
            diff := jsonb_set(diff, array[col],
                '{"old": "[REDACTED]", "new": "[REDACTED]"}'::jsonb);
        end if;
    end loop;
    return diff;
end;
$$;

create or replace function audit_trigger()
returns trigger language plpgsql security definer as $$
declare
    v_user_id uuid;
    v_role    text;
    v_context text;
    v_record  uuid;
    v_diff    jsonb;
    v_action  audit_action;
    old_j     jsonb;
    new_j     jsonb;
    k         text;
begin
    -- Acting identity from connection GUCs (null-safe: workers/system may not set them).
    begin
        v_user_id := nullif(current_setting('app.user_id', true), '')::uuid;
    exception when others then
        v_user_id := null;
    end;
    v_role    := nullif(current_setting('app.user_role', true), '');
    v_context := nullif(current_setting('app.context', true), '');

    if tg_op = 'INSERT' then
        v_action := 'create';
        new_j := to_jsonb(new);
        v_record := (new_j ->> 'id')::uuid;
        -- For creates, log the new values (old = null per field).
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
        -- Field-level old→new for changed fields only.
        v_diff := '{}'::jsonb;
        for k in select jsonb_object_keys(new_j) loop
            if (old_j -> k) is distinct from (new_j -> k) then
                v_diff := v_diff || jsonb_build_object(
                    k, jsonb_build_object('old', old_j -> k, 'new', new_j -> k));
            end if;
        end loop;
        if v_diff = '{}'::jsonb then
            return new;  -- no-op update: nothing to audit
        end if;
    else  -- DELETE
        v_action := 'delete';
        old_j := to_jsonb(old);
        v_record := (old_j ->> 'id')::uuid;
        -- Snapshot the deleted row (new = null per field).
        v_diff := (
            select coalesce(jsonb_object_agg(key, jsonb_build_object('old', value, 'new', null)), '{}'::jsonb)
            from jsonb_each(old_j)
        );
    end if;

    v_diff := audit_redact_secrets(tg_table_name, v_diff);

    insert into audit_log (who_user_id, who_role, entity_table, record_id, action, change_detail, context)
    values (v_user_id, v_role, tg_table_name, v_record, v_action, v_diff, v_context);

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

-- Attach to every audited table (all except audit_log itself; chunk tables are
-- derived artifacts of audited documents but are audited too — "every entity").
do $$
declare
    t text;
begin
    foreach t in array array[
        'firm_settings', 'users', 'cases', 'case_assignments', 'documents',
        'document_chunks', 'ai_outputs', 'deadlines', 'tasks',
        'notifications_log', 'reports_log', 'references_private', 'reference_chunks'
    ]
    loop
        execute format(
            'create trigger trg_audit_%s
             after insert or update or delete on %I
             for each row execute function audit_trigger()', t, t);
    end loop;
end
$$;
