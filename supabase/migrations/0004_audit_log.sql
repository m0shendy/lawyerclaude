-- 0004_audit_log.sql
-- Append-only audit log: who (user + role), when, what (entity + record),
-- action, field-level old→new. [C-III]
-- Written by DB triggers (0005) — cannot be bypassed by an app code path (R6).

create type audit_action as enum ('create', 'update', 'delete');

create table audit_log (
    id            bigint generated always as identity primary key,
    who_user_id   uuid,                 -- null only for system/worker actions
    who_role      text,                 -- role at the time of action
    when_ts       timestamptz not null default now(),
    entity_table  text not null,
    record_id     uuid,
    action        audit_action not null,
    change_detail jsonb,                -- {field: {old: .., new: ..}} — secrets redacted [C-III]
    context       text                  -- screen/endpoint/worker that caused the change
);

create index idx_audit_log_entity on audit_log (entity_table, record_id);
create index idx_audit_log_when on audit_log (when_ts);
create index idx_audit_log_who on audit_log (who_user_id);
