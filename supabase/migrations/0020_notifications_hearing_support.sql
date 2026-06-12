-- 0020_notifications_hearing_support.sql
-- Extend notifications_log to support hearing reminders.
-- Adds hearing_id FK and relaxes the CHECK constraint so any one of
-- (deadline_id, task_id, hearing_id) being non-null satisfies it.

alter table notifications_log
    add column if not exists hearing_id uuid references hearings(id) on delete set null;

create index if not exists idx_notifications_hearing
    on notifications_log (hearing_id) where hearing_id is not null;

-- Drop the old constraint and replace with a broader one.
alter table notifications_log
    drop constraint if exists notifications_log_check;

alter table notifications_log
    add constraint notifications_log_check
    check (
        deadline_id is not null
        or task_id   is not null
        or hearing_id is not null
    );
