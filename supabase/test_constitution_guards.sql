-- Functional test of the constitutional DB guards (run against a freshly
-- migrated scratch DB; used by CI / restore tests). Raises on any failure.
-- Covers: [C-III] audit triggers + append-only, [C-I] RLS role scoping,
-- [C-II] review gate, [C-X] appeal-deadline flag default.

\set ON_ERROR_STOP on

begin;

-- ── fixtures ──────────────────────────────────────────────────────────────
insert into firm_settings (firm_name) values ('Test Firm');

insert into users (id, full_name, email, phone, role) values
  ('00000000-0000-0000-0000-000000000001', 'Manager', 'mgr@t.t',  '+201000000001', 'partner_manager'),
  ('00000000-0000-0000-0000-000000000002', 'Lawyer A', 'law@t.t', '+201000000002', 'lawyer'),
  ('00000000-0000-0000-0000-000000000003', 'Para',    'para@t.t', '+201000000003', 'paralegal');

-- act as the manager for audited writes
select set_config('app.user_id', '00000000-0000-0000-0000-000000000001', false),
       set_config('app.user_role', 'partner_manager', false),
       set_config('app.context', 'test:constitution', false);

insert into cases (id, title, client_name)
  values ('00000000-0000-0000-0000-00000000c001', 'قضية اختبار', 'عميل');
insert into case_assignments (case_id, user_id)
  values ('00000000-0000-0000-0000-00000000c001', '00000000-0000-0000-0000-000000000002');

-- ── [C-III] audit rows captured with who/role/diff ────────────────────────
do $$
declare n int;
begin
  select count(*) into n from audit_log
   where entity_table = 'cases' and action = 'create'
     and who_user_id = '00000000-0000-0000-0000-000000000001'
     and who_role = 'partner_manager' and context = 'test:constitution';
  if n <> 1 then raise exception 'FAIL [C-III]: case create not audited (n=%)', n; end if;
end $$;

update cases set title = 'قضية معدلة' where id = '00000000-0000-0000-0000-00000000c001';

do $$
declare d jsonb;
begin
  select change_detail into d from audit_log
   where entity_table = 'cases' and action = 'update'
   order by id desc limit 1;
  if d -> 'title' ->> 'old' is distinct from 'قضية اختبار'
     or d -> 'title' ->> 'new' is distinct from 'قضية معدلة' then
    raise exception 'FAIL [C-III]: field-level old→new missing: %', d;
  end if;
end $$;

-- ── [C-III] secret redaction ──────────────────────────────────────────────
update firm_settings set llm_api_key = 'super-secret-key-value';

do $$
declare d jsonb;
begin
  select change_detail into d from audit_log
   where entity_table = 'firm_settings' and action = 'update'
   order by id desc limit 1;
  if d::text like '%super-secret-key-value%' then
    raise exception 'FAIL [C-III]: secret value leaked into audit log';
  end if;
  if d -> 'llm_api_key' ->> 'new' is distinct from '[REDACTED]' then
    raise exception 'FAIL [C-III]: secret not redacted as [REDACTED]: %', d;
  end if;
end $$;

-- ── [C-III] append-only ───────────────────────────────────────────────────
do $$
begin
  begin
    update audit_log set context = 'tampered' where id = (select min(id) from audit_log);
    raise exception 'FAIL [C-III]: audit_log UPDATE was allowed';
  exception when others then
    if sqlerrm like 'FAIL%' then raise; end if;  -- our own failure
  end;
  begin
    delete from audit_log where id = (select min(id) from audit_log);
    raise exception 'FAIL [C-III]: audit_log DELETE was allowed';
  exception when others then
    if sqlerrm like 'FAIL%' then raise; end if;
  end;
end $$;

-- ── [C-II] review gate ────────────────────────────────────────────────────
insert into ai_outputs (id, case_id, type, content)
  values ('00000000-0000-0000-0000-0000000000a1',
          '00000000-0000-0000-0000-00000000c001', 'summary', '{"text": "ملخص"}');

do $$
declare s review_state;
begin
  select review_state into s from ai_outputs where id = '00000000-0000-0000-0000-0000000000a1';
  if s <> 'draft_unreviewed' then
    raise exception 'FAIL [C-II]: ai_output not born draft_unreviewed';
  end if;
  if exists (select 1 from ai_outputs_exportable where id = '00000000-0000-0000-0000-0000000000a1') then
    raise exception 'FAIL [C-II]: unapproved output visible in export view';
  end if;
  -- approval without approver must fail
  begin
    update ai_outputs set review_state = 'approved'
     where id = '00000000-0000-0000-0000-0000000000a1';
    raise exception 'FAIL [C-II]: approval without approved_by/at/version allowed';
  exception when check_violation then null;
  end;
end $$;

update ai_outputs
   set review_state = 'approved',
       approved_by = '00000000-0000-0000-0000-000000000002',
       approved_at = now(),
       approved_version = 1
 where id = '00000000-0000-0000-0000-0000000000a1';

do $$
begin
  if not exists (select 1 from ai_outputs_exportable where id = '00000000-0000-0000-0000-0000000000a1') then
    raise exception 'FAIL [C-II]: approved output missing from export view';
  end if;
  -- revert must fail
  begin
    update ai_outputs set review_state = 'draft_unreviewed', approved_by = null,
           approved_at = null, approved_version = null
     where id = '00000000-0000-0000-0000-0000000000a1';
    raise exception 'FAIL [C-II]: approved→draft revert allowed';
  exception when check_violation then null;
  end;
  -- approved content immutable
  begin
    update ai_outputs set content = '{"text": "تلاعب"}'
     where id = '00000000-0000-0000-0000-0000000000a1';
    raise exception 'FAIL [C-II]: approved content mutation allowed';
  exception when check_violation then null;
  end;
end $$;

-- ── [C-X] appeal flag defaults off ─────────────────────────────────────────
do $$
begin
  if (select feature_appeal_deadlines from firm_settings limit 1) then
    raise exception 'FAIL [C-X]: feature_appeal_deadlines not default false';
  end if;
end $$;

-- ── [C-I] RLS: paralegal cannot see unassigned case ────────────────────────
-- (simulate the app role; app_user has no password in scratch — use SET ROLE)
grant app_user to current_user;
set role app_user;
select set_config('app.user_id', '00000000-0000-0000-0000-000000000003', false),
       set_config('app.user_role', 'paralegal', false);

do $$
begin
  if exists (select 1 from cases where id = '00000000-0000-0000-0000-00000000c001') then
    raise exception 'FAIL [C-I]: paralegal sees a case they are not assigned to';
  end if;
end $$;

-- assigned lawyer sees it
select set_config('app.user_id', '00000000-0000-0000-0000-000000000002', false),
       set_config('app.user_role', 'lawyer', false);

do $$
begin
  if not exists (select 1 from cases where id = '00000000-0000-0000-0000-00000000c001') then
    raise exception 'FAIL [C-I]: assigned lawyer cannot see their case';
  end if;
  -- lawyer (non-manager) cannot read firm_settings (secrets)
  if exists (select 1 from firm_settings) then
    raise exception 'FAIL [C-I]: non-manager can read firm_settings secrets';
  end if;
end $$;

reset role;

rollback;  -- scratch validation only — leave the DB untouched

\echo 'ALL CONSTITUTION GUARD TESTS PASSED'
