# Research: SaaS Platform Admin Console

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-06-12

Eight decisions (R1–R8). Each lists Decision / Rationale / Alternatives considered.

---

## R1 — Operator identity: GoTrue user + `platform_operators` allowlist

**Decision**: Operator accounts are ordinary GoTrue users in the **same** Supabase project,
but they are recognized as operators only via a `platform_operators` table row
(`auth_user_id` PK, `is_active`, `created_by`, timestamps). The allowlist row — not any JWT
claim — is the source of truth, checked on every request. No public signup path creates
these rows; provisioning is a documented owner runbook (create GoTrue user in dashboard →
insert allowlist row over the postgres connection → both steps audit-logged).

**Rationale**: [C-XII] requires auth to stay in the one Supabase project, so a second
identity system is out. A DB allowlist gives instant revocation (flip `is_active`),
survives token lifetime, and is itself audit-triggered. JWT custom claims alone would be
valid until expiry even after revocation.

**Alternatives considered**:
- *Separate admin auth system (own password table)* — violates [C-XII]; rejected.
- *`app_metadata.role = 'platform_operator'` claim only* — server-set and tamper-proof,
  but not revocable until token expiry and not audit-triggered; kept only as an optional
  hint, never as the check.
- *Reuse `users` table with a special role* — `users` is a tenant table carrying `firm_id`;
  operators must never be firm members. Rejected.

## R2 — MFA: Supabase Auth TOTP, enforce `aal2`

**Decision**: Operators enroll a TOTP factor (Supabase Auth MFA). The `require_operator`
dependency rejects any operator JWT whose `aal` claim is not `aal2`.

**Rationale**: FR-302 mandates a second factor. GoTrue ships TOTP MFA natively and stamps
the assurance level into the JWT — one claim check server-side, no custom crypto.

**Alternatives considered**: custom TOTP implementation (needless crypto surface); SMS OTP
(weaker, costs money, Egyptian delivery flakiness); WebAuthn (nice-to-have later; TOTP is
the floor).

## R3 — Login flow: backend-proxied password grant with app-level lockout

**Decision**: The admin frontend never talks to GoTrue directly. `POST /admin/login`
receives credentials, checks `operator_login_attempts` for an active lockout (5 fails →
15-min lock), calls GoTrue's password grant server-side, records the attempt
(success/failure, origin IP) and the audit row, then drives the MFA challenge
(`POST /admin/mfa/verify`) the same way. Firm login is unchanged (direct supabase-js).

**Rationale**: FR-303/304 require attempt-level audit and lockout. If the browser talks to
GoTrue directly, the backend never sees failed passwords and can neither count nor log
them. Proxying puts every attempt — success, failure, lockout — through one audited
chokepoint.

**Alternatives considered**: GoTrue's built-in rate limits alone (no per-account lockout,
no audit rows in *our* append-only log); Supabase Auth hooks (cloud-plan dependent, less
portable than a 40-line proxy).

## R4 — Cross-firm data path: service connection + audit GUCs + explicit read audit

**Decision**: `/admin/*` handlers use the existing `SERVICE_DATABASE_URL` connection
(BYPASSRLS) and set the audit GUCs per request: `app.user_id` = operator's auth id,
`app.user_role = 'platform_operator'`, `app.context = 'platform_admin'`. Writes are
captured by the existing audit triggers with full old→new. Cross-firm **reads** that touch
a specific firm (firm detail, audit-viewer queries) additionally INSERT an explicit
audit row (`action = 'admin_read'`, entity, record id, firm id) since triggers don't fire
on SELECT.

**Rationale**: Firm RLS stays byte-identical — no new policies on tenant tables, no
weakening [C-I]. The service role already exists for workers; reusing it avoids a third
DB role. Read logging satisfies FR-311 where triggers cannot.

**Alternatives considered**: a new `app_admin` Postgres role with curated SELECT grants
(cleaner least-privilege, but Supabase Cloud already fought us on BYPASSRLS for
`app_service`; the metadata boundary is enforced at the API layer + `admin_firm_usage`
view either way — revisit if the surface grows); per-table RLS policies for an operator
role (touches every tenant policy, large regression risk on the passed isolation suite).

## R5 — Sessions: `operator_sessions` row per login, 30-min idle, revocable

**Decision**: On successful MFA the backend inserts `operator_sessions`
(`session_id` from the JWT, operator id, `created_at`, `last_seen`). `require_operator`
rejects when the row is missing or `last_seen` is older than 30 minutes, and touches
`last_seen` otherwise. Logout deletes the row. Owner can delete one or all rows
("revoke all sessions") and additionally call GoTrue admin sign-out.

**Rationale**: JWT lifetime is project-global (shared with firm users), so idle timeout
must be enforced app-side. A session row also gives instant, audit-logged revocation
(FR-305) without touching firm token policy.

**Alternatives considered**: shortening project JWT expiry (punishes all firm users);
stateless iat-age check (no revocation, no idle semantics — only login age).

## R6 — Usage metadata: `admin_firm_usage` view, counts only

**Decision**: A SQL view aggregating per-firm counts: users, cases, documents, storage
bytes (sum of `documents.file_size`), ai_outputs, last-activity timestamp. The view's
SELECT list contains **no content columns** — only `firm_id` and aggregates. Operator
endpoints read usage exclusively through this view.

**Rationale**: FR-310's metadata boundary becomes structural: even a buggy handler joined
to this view cannot leak a case title because the view never selects one. Counts are cheap
at current scale; materialize later if needed.

**Alternatives considered**: ad-hoc counts in handler SQL (boundary becomes a code-review
promise instead of a schema fact); per-firm usage table maintained by triggers (more
moving parts than the read rate justifies).

## R7 — Health signals: heartbeat upserts + WAHA session polling

**Decision**: Pipeline and scheduler workers upsert `worker_heartbeats`
(`worker_name` PK, `last_beat`, `details` jsonb) once per tick/pass. `GET /admin/health`
flags any heartbeat older than 5 minutes, and queries WAHA `GET /api/sessions` with the
platform credential, mapping session name (= firm slug) → connected / disconnected /
not provisioned, with a 30-second in-process cache.

**Rationale**: The workers already run on intervals — a one-row upsert is the cheapest
liveness signal that survives container restarts and is queryable from the API. WAHA
already exposes session state; polling read-only respects FR-352.

**Alternatives considered**: Docker-API container inspection (couples the console to the
host runtime and says "running", not "doing work"); push-based webhooks from WAHA (more
setup, same information).

## R8 — Manual payments & event resolutions: separate append-friendly tables, shared activation

**Decision**: `manual_payments` (firm, amount EGP, paid date, reference, mandatory note,
recorded_by operator, created_at) and `billing_event_resolutions` (event id FK, mandatory
note, resolved_by, resolved_at). Recording a manual payment calls the **same**
`activate_subscription()` function the Paymob webhook uses (extracted to
`app/billing/activation.py`). `billing_events` rows are never UPDATEd by reconciliation.

**Rationale**: One activation code path means manual and webhook activation can never
drift ([C-IV] determinism). Resolutions in a side table keep the webhook inbox literally
append-only [C-III] rather than "append-only except for our notes column".

**Alternatives considered**: `resolved_at/note` columns on `billing_events` (mutates the
inbox — rejected on C-III); duplicating activation logic in the admin handler (drift risk
— rejected).
