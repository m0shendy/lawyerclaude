-- 0008_review_gate.sql
-- Review-gate DB guard. [C-II]
-- ai_outputs.review_state already defaults 'draft_unreviewed' (0002) and the
-- approval-consistency CHECK lives on the table. This migration adds:
--   1. an approval guard trigger: approval must set who/when/version, content
--      cannot change in the same statement, and approval cannot be reverted;
--   2. an export-safe view that ONLY exposes approved outputs — the export /
--      official-send code paths read this view, so a non-approved row cannot
--      reach them even through a buggy query. (Defense in depth with the API.)

create or replace function ai_outputs_review_guard()
returns trigger language plpgsql as $$
begin
    -- No path back from approved → draft (a new version is a new row). [C-II]
    if old.review_state = 'approved' and new.review_state = 'draft_unreviewed' then
        raise exception 'review_state cannot revert from approved [C-II]'
            using errcode = 'check_violation';
    end if;

    -- Approval must record who/when/version (the API also audits it). [C-II][C-III]
    if old.review_state = 'draft_unreviewed' and new.review_state = 'approved' then
        if new.approved_by is null or new.approved_at is null or new.approved_version is null then
            raise exception 'approval requires approved_by, approved_at, approved_version [C-II]'
                using errcode = 'check_violation';
        end if;
        -- The content being approved must be exactly the reviewed content.
        if new.content is distinct from old.content then
            raise exception 'content cannot change in the same statement as approval [C-II]'
                using errcode = 'check_violation';
        end if;
    end if;

    -- Approved content is immutable.
    if old.review_state = 'approved' and new.content is distinct from old.content then
        raise exception 'approved output content is immutable [C-II]'
            using errcode = 'check_violation';
    end if;

    return new;
end;
$$;

create trigger trg_ai_outputs_review_guard
    before update on ai_outputs
    for each row execute function ai_outputs_review_guard();

-- Export pathway: reads MUST go through this view. [C-II]
create or replace view ai_outputs_exportable as
    select *
    from ai_outputs
    where review_state = 'approved';

grant select on ai_outputs_exportable to app_user;

comment on view ai_outputs_exportable is
    'The ONLY read path for export/print/attach/official-send. Filters review_state = approved. [C-II]';
