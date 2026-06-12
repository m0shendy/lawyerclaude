# Quickstart: Platform Admin Console — end-to-end smoke test

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Run after implementation, against a staging deployment with two seeded firms
(Firm A active, Firm B trial). ~15 minutes.

## 0. Provision the first operator (one-time, owner runbook)

1. Supabase Dashboard → Auth → Add user (operator email, strong password).
2. Over the postgres connection:
   `insert into platform_operators (auth_user_id, display_name, created_by) values (…)`.
3. Verify both steps appear in `audit_log`.

## 1. Login + MFA (US1)

1. Open `/admin/login` → enter credentials → TOTP enrollment/challenge → land on `/admin`.
2. `select * from operator_login_attempts order by attempted_at desc limit 3` — success row present.
3. Log out; enter the wrong password 5× → 6th attempt returns **locked** with wait time.
4. With a **partner_manager** token, `GET /admin/me` → expect `403`.
5. Wait past idle timeout (or force `last_seen` back 31 min) → any admin action → re-login required.

## 2. Dashboard (US2)

1. `/admin` lists Firm A and Firm B with status, plan, trial expiry, usage counts.
2. Set Firm B's `trial_ends_at` to +2 days → refresh → Firm B carries the attention flag.
3. Confirm no case/document/contact names appear anywhere on the page.
4. Open Firm A detail → `select * from audit_log where action='admin_read' order by at desc limit 1`
   names the operator and Firm A.

## 3. Lifecycle (US3)

1. Suspend Firm A (confirm dialog) → as a Firm A lawyer, call any API → suspension response.
2. `scheduler_worker --once` → Firm A skipped in the pass log.
3. Reactivate Firm A → lawyer access restored.
4. Extend Firm B trial by 7 days → new expiry on dashboard; audit row has old→new dates.
5. Change Firm B plan basic→pro → subscription row updated; audit row present.
6. Cancel a throwaway firm, then try extend-trial on it → `422` rejected.

## 4. Billing oversight (US4)

1. Seed an unprocessed `billing_events` row → it appears in the attention queue; payload viewable.
2. Resolve it **without** a note → blocked. With a note → resolution stored,
   `billing_events` row byte-identical (compare before/after).
3. Record a manual payment for Firm B → `manual_payments` row, subscription `active`,
   firm `active`, audit rows for all three.

## 5. Audit viewer (US5)

1. Filter by Firm A → suspension/reactivation from step 3 visible with old→new diffs.
2. Toggle platform-only → operator actions (incl. logins) listed, distinguishable.
3. Set a firm's LLM key (as firm manager), then view that entry → action-only, no value.
4. Confirm the UI offers no edit/delete affordance on any row.

## 6. Health (US6)

1. `/admin/health` — both workers show fresh heartbeats.
2. `docker stop lc-pipeline` → within 5 min the panel flags pipeline stale → restart it.
3. WAHA session list shows each firm slug with a correct status.

## 7. Isolation suite extension (FR-313 — release gate)

`pytest backend/tests/test_admin_isolation.py` — all six contract checks
(see [contracts/rest-api.md](contracts/rest-api.md) §Isolation-suite additions) green:
firm roles 403 everywhere, aal1 rejected, deactivated operator rejected, idle session
rejected, firm-detail schema work-product-free, no-token fail-closed.

**Done when**: every step above passes and the extended isolation suite is green.

---

## Smoke pass log

T035 (staging smoke on 192.168.5.61) — pending operator authorization to SSH into production server.
