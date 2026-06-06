-- 0006_audit_append_only.sql
-- Append-only enforcement: no app role may edit or delete audit entries. [C-III]
-- audit_trigger() is SECURITY DEFINER (owner inserts), so app roles need
-- nothing beyond SELECT for the manager-only viewer.

revoke all on audit_log from app_user, anon, service_role;
grant select on audit_log to app_user;
grant insert, select on audit_log to service_role;

-- Belt-and-braces: forbid UPDATE/DELETE at the trigger level for every role,
-- including table owners — an audit row, once written, is immutable.
create or replace function audit_log_block_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'audit_log is append-only: % not permitted [C-III]', tg_op;
end;
$$;

create trigger trg_audit_log_immutable
    before update or delete on audit_log
    for each row execute function audit_log_block_mutation();

-- Also block TRUNCATE.
create or replace function audit_log_block_truncate()
returns trigger language plpgsql as $$
begin
    raise exception 'audit_log is append-only: TRUNCATE not permitted [C-III]';
end;
$$;

create trigger trg_audit_log_no_truncate
    before truncate on audit_log
    for each statement execute function audit_log_block_truncate();
