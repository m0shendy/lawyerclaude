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

1. **API**: `uvicorn app.main:create_app --factory` behind the host's TLS.
   Health: `GET /health`.
2. **Workers**: `python -m workers.pipeline_worker` and
   `python -m workers.scheduler_worker` (the scheduler also flips expired
   trials to `suspended` in its daily pass).
3. **Frontend**: Vercel, env `NEXT_PUBLIC_API_URL=https://api.<domain>`.
4. **Paymob dashboard**: set the *Transaction processed callback* to
   `https://api.<domain>/billing/paymob-webhook`. Send one sandbox payment and
   confirm `billing_events` gets the txn row and the firm flips to `active`.
5. **WAHA**: start WAHA Plus; for each paying firm create a session named by
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

## 7. Operations quick reference

* Suspend a firm now: `update firms set status='suspended' where slug=...;`
  (API returns 402-style responses; workers skip it next pass).
* Audit a firm: `select * from audit_log where firm_id=... order by id desc;`
* Pricing lives in `backend/app/billing/__init__.py` (PLANS) — amounts are
  reconciled server-side against this table; changing a price here changes
  what webhooks will accept.
* Adding a billing provider: implement alongside `app/billing/paymob.py`;
  webhooks must keep the three invariants — signature verification,
  idempotent `billing_events` inbox, server-side amount reconciliation.
