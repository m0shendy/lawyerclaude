# SAAS RUNBOOK — lawyerclaude multi-tenant deployment (constitution v2)

One application stack serves all firms. Isolation is fail-closed RLS [C-I v2].
This runbook is the deployment path that replaced `infra/legacy/` (per-firm
stacks). Current state when this was written: the Supabase Cloud project
**`iwnvcafoubetxenifcjr`** (eu-central-1) already exists with migrations
0001–0013 + cloud-hardening applied and the 12-check isolation suite passed.

## 1. Topology

| Component | Where | Notes |
|---|---|---|
| Postgres + pgvector, GoTrue, Storage | Supabase Cloud (one project) | PITR backups on Pro plan |
| FastAPI API | Any container host (Railway / Fly / Hetzner VPS) | 1+ replicas |
| pipeline_worker, scheduler_worker | Same host, separate processes | exactly 1 scheduler_worker |
| Next.js frontend | Vercel | `NEXT_PUBLIC_API_URL` → API host |
| WAHA Plus (WhatsApp) | Same container host | one session per firm (slug) |

## 2. One-time database setup (DONE for the current project — repeat only for a new env)

1. Create the Supabase project; run migrations `0001` → `0013` in order, then the
   cloud-hardening migrations (audit_log RLS, API-role lockdown, helper EXECUTE grants).
2. Set DB role passwords (Dashboard → SQL editor, as `postgres`):
   ```sql
   alter role app_user    with password '<strong-secret-1>';
   alter role app_service with password '<strong-secret-2>';
   ```
   ⚠ Supabase Cloud may refuse BYPASSRLS on `app_service`. Check:
   `select rolbypassrls from pg_roles where rolname='app_service';`
   If `false`, point `SERVICE_DATABASE_URL` at the `postgres` user connection
   string instead — workers must NOT run RLS-filtered. Verify either way:
   a worker connection must see rows of ALL firms.
3. Run the adversarial isolation suite (two seeded firms, 12 checks — see
   constitution Principle I). MUST be green before real data enters. [C-I v2]

## 3. Backend environment (API + workers)

```
DATABASE_URL=postgresql://app_user:...@db.<ref>.supabase.co:5432/postgres
SERVICE_DATABASE_URL=postgresql://app_service:...@db.<ref>.supabase.co:5432/postgres
GOTRUE_JWT_SECRET=<Dashboard → Settings → API → JWT secret>
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_KEY=<service_role key — SECRET, server-side only>
STORAGE_BUCKET=documents
# Google Document AI (platform credential — OCR runs under the platform account)
DOCAI_PROJECT_ID=... DOCAI_LOCATION=eu DOCAI_PROCESSOR_ID=...
GOOGLE_APPLICATION_CREDENTIALS=/secrets/docai.json
# Paymob (billing) — all four required before /billing/initiate works
PAYMOB_API_KEY=...        PAYMOB_INTEGRATION_ID=...
PAYMOB_IFRAME_ID=...      PAYMOB_HMAC_SECRET=...
CORS_ORIGINS=https://app.<your-domain>
```

Use **session-mode / direct** connections (port 5432), NOT the transaction
pooler (6543): the RLS GUCs (`app.firm_id` etc.) are set per connection and a
transaction pooler breaks that contract. If you must pool, use Supavisor in
session mode.

## 4. Deploy order

Use `infra/docker-compose.yml` — it runs **only** frontend, backend, and workers.
All Postgres/Auth/Storage lives on Supabase Cloud; nothing local is started.

```bash
# On the host (192.168.5.61):
cd /opt/firms/lawyer
# ensure infra/.env does not exist (env file lives at /opt/firms/lawyer/.env)
docker compose -f infra/docker-compose.yml pull  # or build
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml ps    # all 4 services should be Up
```

Services started: `backend`, `worker-pipeline`, `worker-scheduler`, `frontend`.
Health: `GET /health` on the backend should return `{"status":"ok"}`.

1. **Paymob dashboard**: set the *Transaction processed callback* to
   `https://api.<domain>/billing/paymob-webhook`. Send one sandbox payment and
   confirm `billing_events` gets the txn row and the firm flips to `active`.
2. **WAHA**: start WAHA Plus; for each paying firm create a session named by
   the firm slug and store `waha_url`/`waha_key` in that firm's settings page.

## 5. Smoke test (every deploy)

1. `/signup` a throwaway firm → login → create case → upload a scanned PDF →
   pipeline reaches `ready` → ask the assistant about the document → output is
   `draft_unreviewed` → approve → export works. [C-II]
2. With a SECOND throwaway firm, verify it sees none of the first firm's data.
3. `python -m workers.scheduler_worker --once` → notifications_log rows appear
   for due items of BOTH firms (and only their own).

## 6. Backups & restore test [C-XI / T101]

Supabase Pro gives daily backups + PITR. That does NOT discharge T101:
quarterly, restore the latest backup into a scratch Supabase project, run the
isolation suite + `pytest` smoke against it, record the evidence in
`docs/restore-tests.md`. An untested backup is not a backup.

## 7. Platform Operator Provisioning & Revocation

The `/admin/*` console is accessible only to **platform operators** — distinct from all
firm users. There is no public signup path for operators. Every operator must be
provisioned manually by an existing operator or directly via the database.

### 7.1 Provision a new operator

```sql
-- Step 1: create a GoTrue user (must use Supabase Dashboard or Management API)
-- Dashboard → Authentication → Users → Invite / Create user
-- Note the new user's UUID (auth.users.id) — call it <AUTH_UUID>

-- Step 2: register in the allowlist
INSERT INTO platform_operators (auth_user_id, display_name, is_active, created_by)
VALUES ('<AUTH_UUID>', 'Operator Name', true, '<YOUR_AUTH_UUID>');
```

### 7.2 First login + TOTP enrollment

1. Operator navigates to `/admin/login`.
2. Enters email + password → backend proxies to GoTrue.
3. If no TOTP factor enrolled yet: response has `mfa_enrollment_required: true` →
   UI shows the QR code for enrollment (`POST /admin/mfa/enroll`).
4. Operator scans QR with authenticator app and submits the 6-digit code
   (`POST /admin/mfa/verify`) → receives `access_token`.
5. Token is stored in `sessionStorage` (clears on tab close).

**TOTP enrollment is mandatory.** A password-only (aal1) token is rejected by
every `/admin/*` route. The console is unusable without a TOTP factor.

### 7.3 Revoke a single operator session

```sql
-- From Supabase SQL editor or psql with service role:
DELETE FROM operator_sessions WHERE operator_id = '<AUTH_UUID>';
```

Or use the console itself: **Settings → Revoke all sessions** button
(`POST /admin/sessions/revoke-all` — terminates ALL operator sessions simultaneously,
forcing re-authentication on next access).

### 7.4 Deactivate an operator

```sql
UPDATE platform_operators SET is_active = false WHERE auth_user_id = '<AUTH_UUID>';
-- Immediately blocks all future requests even if a session token exists.
-- Does NOT delete the audit trail for past actions.
```

### 7.5 Emergency lockout (all operators)

```sql
-- Nuke all live sessions — forces re-auth for everyone:
DELETE FROM operator_sessions;
```

### 7.6 Lockout policy

Backend enforces: ≥ 5 failed password attempts within 15 minutes → 423 Locked.
The lockout resets automatically when a successful login is recorded within the window,
or after the 15-minute window passes with no new failures.

---

## 8. Operations quick reference

* Suspend a firm now: `update firms set status='suspended' where slug=...;`
  (API returns 402-style responses; workers skip it next pass).
* Audit a firm: `select * from audit_log where firm_id=... order by id desc;`
* Pricing lives in `backend/app/billing/__init__.py` (PLANS) — amounts are
  reconciled server-side against this table; changing a price here changes
  what webhooks will accept.
* Adding a billing provider: implement alongside `app/billing/paymob.py`;
  webhooks must keep the three invariants — signature verification,
  idempotent `billing_events` inbox, server-side amount reconciliation.
