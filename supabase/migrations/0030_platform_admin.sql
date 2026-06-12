-- 0030_platform_admin.sql
-- Feature 003: SaaS Platform Admin Console.
-- Six new platform tables + one metadata-only aggregate view.
-- All tables are service-context only: zero grants to app_user.
-- Fail-closed by design: a compromised firm session cannot even SELECT these. [C-I][C-III]

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. platform_operators — operator allowlist (R1)
-- ─────────────────────────────────────────────────────────────────────────────
create table platform_operators (
    auth_user_id  uuid        primary key references auth.users (id),
    display_name  text        not null,
    is_active     boolean     not null default true,
    created_by    uuid        references auth.users (id),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. operator_sessions — live operator sessions (R5)
--    State machine: active (row exists, last_seen < 30 min) →
--    idle-expired (stale → rejected + lazily purged) → revoked (deleted).
-- ─────────────────────────────────────────────────────────────────────────────
create table operator_sessions (
    session_id  text        primary key,
    operator_id uuid        not null references platform_operators (auth_user_id) on delete cascade,
    created_at  timestamptz not null default now(),
    last_seen   timestamptz not null default now()
);

create index idx_operator_sessions_operator on operator_sessions (operator_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. operator_login_attempts — lockout ledger (R3)
--    App layer: ≥5 failures for an email in 15 min, no intervening success ⇒ 423.
-- ─────────────────────────────────────────────────────────────────────────────
create table operator_login_attempts (
    id           uuid        primary key default gen_random_uuid(),
    email        text        not null,
    succeeded    boolean     not null,
    origin_ip    text,
    attempted_at timestamptz not null default now()
);

create index idx_login_attempts_email_time on operator_login_attempts (email, attempted_at desc);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. manual_payments — operator-recorded payments (R8)
--    Side effect (code, not trigger): calls activate_subscription().
-- ─────────────────────────────────────────────────────────────────────────────
create table manual_payments (
    id          uuid           primary key default gen_random_uuid(),
    firm_id     uuid           not null references firms (id),
    amount_egp  numeric(12, 2) not null check (amount_egp > 0),
    paid_date   date           not null,
    reference   text           not null,
    note        text           not null,
    recorded_by uuid           not null references platform_operators (auth_user_id),
    created_at  timestamptz    not null default now()
);

create index idx_manual_payments_firm on manual_payments (firm_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. billing_event_resolutions — append-only inbox companion (R8)
--    billing_events itself is NEVER updated. [C-III]
-- ─────────────────────────────────────────────────────────────────────────────
create table billing_event_resolutions (
    id               uuid        primary key default gen_random_uuid(),
    billing_event_id uuid        not null unique references billing_events (id),
    note             text        not null,
    resolved_by      uuid        not null references platform_operators (auth_user_id),
    resolved_at      timestamptz not null default now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. worker_heartbeats — liveness signals (R7)
--    No audit trigger: updates every few seconds, holds no firm/secret data;
--    flooding the audit log has zero accountability value. Documented deviation.
-- ─────────────────────────────────────────────────────────────────────────────
create table worker_heartbeats (
    worker_name text        primary key,
    last_beat   timestamptz not null default now(),
    details     jsonb       not null default '{}'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Audit triggers on the five accountable tables (NOT worker_heartbeats). [C-III]
-- ─────────────────────────────────────────────────────────────────────────────
select attach_audit_trigger('platform_operators');
select attach_audit_trigger('operator_sessions');
select attach_audit_trigger('operator_login_attempts');
select attach_audit_trigger('manual_payments');
select attach_audit_trigger('billing_event_resolutions');

-- ─────────────────────────────────────────────────────────────────────────────
-- Grants — FAIL-CLOSED: zero grants to app_user on any of these tables.
-- Service context only (require_operator-gated API + worker heartbeat upserts).
-- ─────────────────────────────────────────────────────────────────────────────
-- No grant statements needed: tables are not accessible to app_user by default.
-- service_role (BYPASSRLS) can already access all tables.

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. admin_firm_usage — metadata-only aggregate view (R6)
--    Boundary: the SELECT list contains ONLY counts and timestamps — no content
--    columns. Operator usage queries go through this view exclusively. [FR-310]
--    Note: documents has no file_size column (storage via Supabase Storage);
--    storage_bytes is exposed as 0 until a file_size column is added.
-- ─────────────────────────────────────────────────────────────────────────────
create view admin_firm_usage as
select
    f.id as firm_id,
    (select count(*) from users       u where u.firm_id = f.id)            as user_count,
    (select count(*) from cases       c where c.firm_id = f.id)            as case_count,
    (select count(*) from documents   d where d.firm_id = f.id)            as document_count,
    0::bigint                                                               as storage_bytes,
    (select count(*) from ai_outputs  a where a.firm_id = f.id)            as ai_output_count,
    (select max(al.when_ts) from audit_log al where al.firm_id = f.id)     as last_activity_at
from firms f;

-- Service role can read the view; app_user cannot (not granted).
grant select on admin_firm_usage to service_role;
