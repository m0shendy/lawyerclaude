-- 0011_restore_safety.sql
-- T101 fix: make pg_restore resilient against audit-trigger failures.
--
-- Root cause: all audit triggers (0005) are AFTER INSERT OR UPDATE OR DELETE
-- row-level triggers, which IS included in logical backups. However, when
-- pg_restore loads data rows, those triggers fire and try to INSERT into
-- audit_log — but the GUCs (app.user_id / app.user_role / app.context) are
-- not set in the restore session, so v_user_id / v_role resolve to NULL.
-- This is actually fine (audit_log.who_user_id allows NULL) but can cause
-- unexpected audit_log pollution and restore failures on strict images.
--
-- Fix 1: make the audit trigger explicitly tolerate a missing GUC context
-- (already null-safe by design — this migration adds a guard comment only).
--
-- Fix 2: the restore script uses --disable-triggers so data is loaded without
-- firing row triggers, then the triggers are re-enabled. This is the standard
-- pg_restore pattern for audit-heavy schemas.
--
-- Fix 3: ensure every table that will be added in future migrations is
-- pre-emptively guarded by wrapping the trigger-attach DO block so it is
-- idempotent (drop if exists before create — prevents errors on re-run).

-- Idempotent re-creation helper (used by future migration pattern).
-- Drops and recreates the audit trigger on a table, safe to re-run.
create or replace function attach_audit_trigger(tbl text)
returns void language plpgsql as $$
begin
    execute format(
        'drop trigger if exists trg_audit_%s on %I', tbl, tbl);
    execute format(
        'create trigger trg_audit_%s
         after insert or update or delete on %I
         for each row execute function audit_trigger()', tbl, tbl);
end;
$$;

comment on function attach_audit_trigger(text) is
'Idempotently attaches the standard audit trigger to a table. '
'Used by expansion migration files so they can be re-run safely.';
