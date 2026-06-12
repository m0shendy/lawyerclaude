# REST API Contract: /admin/* (Platform Operator Surface)

**Feature**: [../spec.md](../spec.md) · **Plan**: [../plan.md](../plan.md)

All endpoints live under the `/admin` prefix in `backend/app/api/admin.py`. Every endpoint
except `login` and `mfa/verify` requires the `require_operator` dependency:
**valid ES256 JWT → `aal2` → active `platform_operators` row → fresh `operator_sessions`
row (<30 min idle)**. Any failed link ⇒ `401`/`403` with no data (fail-closed, FR-312).
Firm-role tokens of every kind MUST receive `403` (FR-303) and the attempt is audit-logged.

## Authentication

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| POST | /admin/login | `{email, password}` | `200 {mfa_required: true, factor_id, challenge_token}` · `401` bad credentials · `423` locked | Backend-proxied GoTrue grant. Lockout: 5 fails/15 min (R3). Every attempt → `operator_login_attempts` + audit row |
| POST | /admin/mfa/verify | `{factor_id, challenge_token, code}` | `200 {access_token, expires_in}` · `401` | On success: allowlist check, `operator_sessions` insert, audit row |
| POST | /admin/logout | — | `204` | Deletes session row; audit row |
| GET | /admin/me | — | `200 {operator_id, display_name, session_created_at}` | Probe endpoint; used by isolation suite |
| POST | /admin/sessions/revoke-all | — | `204` | Deletes all operator sessions (incident response); audit row |

## Firms

| Method | Path | Body / Query | Returns | Notes |
|---|---|---|---|---|
| GET | /admin/firms | `?status=&plan=&q=&page=` | `200 [{id, name, slug, status, plan, trial_ends_at, created_at, attention_flags[]}]` | List view; `attention_flags`: `trial_expiring`, `payment_failed`, `unprocessed_event` |
| GET | /admin/firms/{id} | — | `200 {firm, subscription, usage}` | `usage` from `admin_firm_usage` (counts only). **Writes `admin_read` audit row** (FR-311) |
| POST | /admin/firms/{id}/suspend | `{confirm: true}` | `200 {status}` · `409` already suspended | Audit old→new |
| POST | /admin/firms/{id}/reactivate | `{confirm: true}` | `200 {status}` | Audit old→new |
| POST | /admin/firms/{id}/cancel | `{confirm: true}` | `200 {status}` | Audit old→new |
| POST | /admin/firms/{id}/extend-trial | `{days: 1..90, confirm: true}` | `200 {trial_ends_at}` · `422` firm cancelled (FR-321) | Audit old→new dates |
| POST | /admin/firms/{id}/change-plan | `{plan, confirm: true}` | `200 {plan}` | Administrative only — moves no money (FR-322) |

## Billing oversight

| Method | Path | Body / Query | Returns | Notes |
|---|---|---|---|---|
| GET | /admin/subscriptions | `?status=&firm_id=` | `200 [{firm_id, firm_name, plan, provider, status, current_period_end}]` | FR-330 |
| GET | /admin/billing-events | `?unprocessed=true&firm_hint=&page=` | `200 [{id, provider, provider_ref, received_at, processed_at, resolved, payload}]` | Inbox view; payload is the firm's own webhook data (FR-331) |
| POST | /admin/billing-events/{id}/resolve | `{note}` (note mandatory) | `201 {resolution_id}` · `409` already resolved | Inserts `billing_event_resolutions`; event row untouched (FR-333) |
| POST | /admin/firms/{id}/manual-payment | `{amount_egp, paid_date, reference, note, confirm: true}` | `201 {payment_id, subscription_status, firm_status}` | Calls shared `activate_subscription()` (R8); audit-logged (FR-332) |

## Audit viewer

| Method | Path | Query | Returns | Notes |
|---|---|---|---|---|
| GET | /admin/audit | `?firm_id=&actor=&entity=&action=&from=&to=&platform_only=&page=` | `200 [{at, who, role, context, entity, record_id, action, old, new}]` | Read-only. Secret-change rows arrive pre-redacted (action-only) from the trigger layer (FR-342). **Each query writes an `admin_read` audit row** |

## Operational health

| Method | Path | Returns | Notes |
|---|---|---|---|
| GET | /admin/health | `200 {workers: [{name, last_beat, stale}], waha_sessions: [{firm_slug, status}], recent_signups: [{firm, created_at}]}` | `stale` = last_beat > 5 min. WAHA polled with 30 s cache (R7). Strictly read-only (FR-352) |

## Error envelope

Same envelope as the rest of the API. Notables: `423 Locked` (login lockout),
`403` for any firm-role token on any `/admin/*` path, `401` for missing/expired/aal1
tokens and idle-expired sessions.

## Isolation-suite additions (FR-313, release gate)

1. Each firm role (partner_manager, lawyer, paralegal, secretary, client/portal) calls
   every `/admin/*` endpoint → expect `403`, audit row written.
2. Operator token at `aal1` (no MFA) → `401` on `/admin/me`.
3. Operator with `is_active=false` allowlist row → `403` despite valid aal2 token.
4. Idle session (last_seen forced >30 min) → `401`, re-login required.
5. `GET /admin/firms/{id}` response schema contains zero work-product fields
   (case titles, document names, contact names) — schema asserted, not eyeballed.
6. No-token request to every `/admin/*` endpoint → `401`, zero bytes of data.
