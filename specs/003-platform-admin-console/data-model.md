# Data Model: SaaS Platform Admin Console

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-06-12
**Migration**: `supabase/migrations/0030_platform_admin.sql`

Six new tables + one view. All new tables are **platform tables** (no `firm_id`, no firm
RLS) and are reachable **only** over the service connection — `app_user` receives **no
grants** on any of them, so a compromised firm session cannot even SELECT them
(fail-closed, FR-312). All six get the standard audit trigger
(`attach_audit_trigger`) **[C-III]**.

---

## platform_operators — operator allowlist (R1)

| Column | Type | Notes |
|---|---|---|
| auth_user_id | uuid PK | references `auth.users(id)`; the GoTrue account |
| display_name | text not null | shown in audit attribution |
| is_active | boolean not null default true | flip false = instant revocation |
| created_by | uuid | references auth.users(id); the owner who provisioned |
| created_at / updated_at | timestamptz | |

Constraints: an operator MUST NOT also exist in the tenant `users` table (enforced at
provisioning runbook + a CHECK is impossible cross-table; verified by isolation suite).

## operator_sessions — live operator sessions (R5)

| Column | Type | Notes |
|---|---|---|
| session_id | text PK | GoTrue JWT `session_id` claim |
| operator_id | uuid not null | references platform_operators(auth_user_id) on delete cascade |
| created_at | timestamptz not null default now() | |
| last_seen | timestamptz not null default now() | touched on every authorized request |

State machine: `active` (row exists, `last_seen` < 30 min ago) → `idle-expired`
(row exists, stale → request rejected, row purged lazily) → `revoked` (row deleted by
logout or owner revoke-all). No other states.

## operator_login_attempts — lockout ledger (R3)

| Column | Type | Notes |
|---|---|---|
| id | uuid PK default gen_random_uuid() | |
| email | text not null | attempted identity (operators are few; plain index) |
| succeeded | boolean not null | |
| origin_ip | text | |
| attempted_at | timestamptz not null default now() | |

Lockout rule (app layer): ≥5 rows with `succeeded=false` for an email in the last 15
minutes and no intervening success ⇒ reject before GoTrue is called. Successful login
inserts a success row (resets the window).

## manual_payments — operator-recorded payments (R8)

| Column | Type | Notes |
|---|---|---|
| id | uuid PK default gen_random_uuid() | |
| firm_id | uuid not null references firms(id) | target firm |
| amount_egp | numeric(12,2) not null check (> 0) | |
| paid_date | date not null | |
| reference | text not null | bank/transfer reference |
| note | text not null | mandatory context |
| recorded_by | uuid not null references platform_operators(auth_user_id) | |
| created_at | timestamptz not null default now() | |

Side effect (code, not trigger): calls shared `activate_subscription(firm_id, …)` —
same function as the Paymob webhook.

## billing_event_resolutions — append-only inbox companion (R8)

| Column | Type | Notes |
|---|---|---|
| id | uuid PK default gen_random_uuid() | |
| billing_event_id | uuid not null references billing_events(id) | unique — one resolution per event |
| note | text not null | mandatory |
| resolved_by | uuid not null references platform_operators(auth_user_id) | |
| resolved_at | timestamptz not null default now() | |

`billing_events` itself is **never** UPDATEd by reconciliation **[C-III]**.

## worker_heartbeats — liveness signals (R7)

| Column | Type | Notes |
|---|---|---|
| worker_name | text PK | `pipeline_worker`, `scheduler_worker` |
| last_beat | timestamptz not null default now() | upserted each tick/pass |
| details | jsonb not null default '{}' | e.g. last pass counts |

No audit trigger on this table only — it updates every few seconds and would flood the
audit log with zero accountability value (documented deviation; the table holds no firm
or secret data). All other five tables are audit-triggered.

## admin_firm_usage — metadata-only aggregate view (R6)

```sql
create view admin_firm_usage as
select f.id as firm_id,
       (select count(*) from users      u where u.firm_id = f.id)             as user_count,
       (select count(*) from cases      c where c.firm_id = f.id)             as case_count,
       (select count(*) from documents  d where d.firm_id = f.id)             as document_count,
       (select coalesce(sum(d.file_size),0) from documents d
         where d.firm_id = f.id)                                              as storage_bytes,
       (select count(*) from ai_outputs a where a.firm_id = f.id)             as ai_output_count,
       (select max(al.at) from audit_log al where al.firm_id = f.id)          as last_activity_at
from firms f;
```

The SELECT list is the boundary: **no content columns exist in this view**. Operator
usage queries go through it exclusively (FR-310). View is service-context only (no
`app_user` grant). Column names verified against the live schema at migration time.

---

## Existing tables touched

| Table | Change |
|---|---|
| firms | none structural — `status`, `trial_ends_at` become operator-writable via service path (already writable there) |
| subscriptions | none structural — `plan`, `status`, `current_period_end` operator-writable via shared activation |
| billing_events | none — explicitly untouched (append-only) |
| audit_log | none structural — gains rows with `app.context='platform_admin'` and explicit `admin_read` action rows |

## Grants summary (fail-closed)

```text
platform_operators, operator_sessions, operator_login_attempts,
manual_payments, billing_event_resolutions, worker_heartbeats, admin_firm_usage
    → NO grant to app_user            (firm sessions cannot see they exist)
    → service context only            (require_operator-gated API + workers' heartbeat upsert)
```

## Audit coverage matrix

| Entity | trigger (writes) | explicit read audit |
|---|---|---|
| platform_operators | ✅ | — |
| operator_sessions | ✅ | — |
| operator_login_attempts | ✅ (each attempt is an insert) | — |
| manual_payments | ✅ | — |
| billing_event_resolutions | ✅ | — |
| worker_heartbeats | ✗ (documented exception above) | — |
| firms / subscriptions (operator writes) | ✅ existing triggers, operator GUCs | — |
| firm detail view, audit-viewer queries | n/a | ✅ `admin_read` rows (FR-311) |
