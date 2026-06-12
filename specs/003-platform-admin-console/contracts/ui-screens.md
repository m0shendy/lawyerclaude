# UI Screens Contract: Platform Admin Console

**Feature**: [../spec.md](../spec.md) · **Plan**: [../plan.md](../plan.md)

All screens live under the `frontend/app/admin/**` route group with a dedicated layout
(`admin/layout.tsx`): its own minimal nav, operator-session guard (no session → redirect
`/admin/login`), and **no reuse of the firm AppNav** — an operator can never "wander" into
firm screens with operator context, and firm users never see admin nav items. RTL Arabic,
same design system.

| Screen | Route | Access | Shows | Actions |
|---|---|---|---|---|
| Operator login | `/admin/login` | public (page), backend-gated (function) | email+password form → TOTP code step | login, verify MFA. Errors: bad credentials, locked (with remaining time), bad code |
| Firms dashboard | `/admin` | operator | all firms table: name, slug, status badge, plan, trial expiry, user/case/doc counts; attention strip (trials expiring ≤3 d, payment issues); search + status/plan filters | row click → firm detail |
| Firm detail | `/admin/firms/[id]` | operator | firm card (status, plan, trial, created), usage counts panel, subscription panel, recent platform events for this firm | suspend / reactivate / cancel / extend trial (days input) / change plan — **each behind a confirm dialog** stating the consequence; dismiss = no-op (US3-5) |
| Billing oversight | `/admin/billing` | operator | subscriptions table; billing-events inbox with unprocessed/problem queue; payload viewer (modal) | resolve event (mandatory note), record manual payment (form: amount EGP, date, reference, note, confirm) |
| Audit viewer | `/admin/audit` | operator | filterable audit table (firm, actor, entity, action, date range, platform-only toggle); row expand → field-level old→new diff; secret rows render "🔑 action-only" | filter, paginate only — **no mutation affordances exist** (FR-340–342) |
| Health panel | `/admin/health` | operator | worker cards (name, last heartbeat, stale flag), WAHA session list (firm slug → connected/disconnected/not provisioned), recent signups feed | refresh only — read-only (FR-352) |

## Cross-cutting UI rules

- **Session expiry**: any 401 from `/admin/*` clears local state and redirects to
  `/admin/login` with an "انتهت الجلسة" notice.
- **Metadata boundary is visual too**: no screen has a column, tooltip, link, or search
  result that names a case, document, contact, or client of a firm (FR-310).
- **Confirm dialogs** name the firm and the exact consequence ("سيُمنع موظفو المكتب من
  الدخول فورًا") and require an explicit checkbox + button.
- **Every action's result** surfaces the audit fact: success toasts include "تم تسجيل
  الإجراء في سجل التدقيق".
- **No link from any firm-facing screen** points into `/admin/**`, and `/admin/**` is
  excluded from any firm-facing sitemap/nav component.
