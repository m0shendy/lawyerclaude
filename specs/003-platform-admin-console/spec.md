# Feature Specification: SaaS Platform Admin Console

**Feature Directory**: `specs/003-platform-admin-console`
**Created**: 2026-06-12
**Status**: Draft
**Scope**: A platform-level (super-admin) area, completely separate from firm staff logins
and the client portal, used by the SaaS operator to run the multi-tenant platform: secure
operator login, a dashboard of all firms, firm lifecycle management (suspend / reactivate /
extend trial / change plan), subscription & billing oversight with manual reconciliation,
platform-wide audit log viewing, and operational health (per-firm WhatsApp session status,
worker heartbeats).

> **Constitution binding**: This spec is subordinate to the project constitution
> (`.specify/memory/constitution.md`, v2). Constitutional anchors are referenced inline as
> **[C-I]** … **[C-XII]**. Where this spec and the constitution conflict, the constitution
> wins and the conflict must be surfaced.
>
> **Constitutional tension — declared up front**: Principle **[C-I]** establishes fail-closed
> per-firm isolation with no cross-firm access path. The platform operator is, by definition,
> the **single sanctioned exception**: the only role that may see data spanning firms. This
> spec resolves the tension as follows — the operator surface is a separate, explicitly
> authorized context; it never weakens or bypasses firm-level RLS for any other role; it is
> restricted to **operational metadata** (never firm work product); and **every** cross-firm
> read and write it performs is audit-logged **[C-III]**. The adversarial isolation suite is
> extended to prove that no firm credential, of any role, can reach any operator endpoint.
>
> **Foundation specs**: Builds on
> [specs/001-lawyer-office-management/spec.md](../001-lawyer-office-management/spec.md) and
> [specs/002-legal-platform-expansion/spec.md](../002-legal-platform-expansion/spec.md).
> All prior requirements remain in force.

---

## Roles

| Role             | Change   | Scope                                                            |
|------------------|----------|------------------------------------------------------------------|
| partner_manager  | existing | Firm-scoped only. **No access** to any operator surface.         |
| lawyer / paralegal / secretary | existing | Firm-scoped only. No operator access.              |
| client           | existing | Portal only. No operator access.                                 |
| **platform_operator** | **new** | Cross-firm **operational metadata** only. Cannot read or write firm work product (cases, documents, AI outputs, contacts, billing details of a firm's clients). |

A platform_operator account is a distinct account type. Firm staff credentials — including
partner_manager — can never grant operator access, and an operator account cannot be used to
log into a firm's workspace.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Secure Operator Login (Priority: P1)

The platform operator signs in at a dedicated operator entry point, separate from the firm
login page and the client portal. Sign-in requires a second factor. Failed attempts are
rate-limited and lockout applies after repeated failures. Every login attempt — success or
failure — is audit-logged. Operator sessions expire after a short idle period and can be
revoked.

**Why this priority**: Nothing else in this feature may exist until the entry point is
provably restricted. A compromised operator account is a platform-wide breach, so the bar is
higher than for any firm role. **[C-XI]**

**Independent Test**: Attempt operator login with (a) valid operator credentials + second
factor → success, audit-logged; (b) valid **firm** credentials of every role → rejected;
(c) repeated bad passwords → lockout; (d) expired session → re-authentication required.

**Acceptance Scenarios**:

1. **Given** a provisioned operator account, **When** the operator signs in with correct
   credentials and second factor, **Then** access is granted and the login is audit-logged
   with who/when/origin.
2. **Given** any firm staff or client credential, **When** it is presented to the operator
   entry point or any operator function, **Then** access is denied and the attempt is
   audit-logged.
3. **Given** N consecutive failed attempts (default 5), **When** the next attempt arrives,
   **Then** the account is temporarily locked and the lockout is audit-logged.
4. **Given** an idle operator session past the timeout (default 30 minutes), **When** the
   operator acts, **Then** re-authentication is required.
5. **Given** an active operator session, **When** the owner revokes it, **Then** the session
   is invalidated immediately.

---

### User Story 2 — All-Firms Dashboard (Priority: P1)

The operator opens the console and sees every firm on the platform: name, slug, status
(trial / active / past_due / suspended / cancelled), plan, trial expiry, signup date, and
operational usage metadata (user count, case count, document count, storage used — counts
only, never content). The list is searchable and filterable by status and plan. Firms whose
trials expire soon, or whose payments have failed, are visually surfaced.

**Why this priority**: This is the operator's situational awareness — the reason the console
exists. Every management action in later stories starts from this view.

**Independent Test**: Seed two firms in different states; verify both appear with correct
status/plan/trial data, that usage numbers are counts only, and that filtering and the
"attention needed" surfacing work.

**Acceptance Scenarios**:

1. **Given** firms in assorted states, **When** the dashboard loads, **Then** all firms are
   listed with status, plan, trial expiry, and usage counts.
2. **Given** a firm whose trial expires within 3 days, **When** the dashboard loads, **Then**
   that firm is flagged as needing attention.
3. **Given** the operator views any firm, **Then** the view exposes **no** firm work product —
   no case titles, document names, contact names, AI outputs, or client identities — only
   aggregate counts and platform metadata. *(Reading a firm's detail view is itself an
   audit-logged cross-firm read **[C-III]**.)*
4. **Given** a search by firm name or slug, **When** submitted, **Then** matching firms are
   returned.

---

### User Story 3 — Firm Lifecycle Management (Priority: P1)

From a firm's detail view the operator can: suspend the firm (immediately blocks its access),
reactivate it, extend its trial by a chosen number of days, change its plan, or cancel it.
Each action requires explicit confirmation, takes effect platform-wide promptly, and is
audit-logged with who/when/what/old→new.

**Why this priority**: This is the operational core — without it the operator still runs the
platform over raw SQL, which is exactly what this feature retires.

**Independent Test**: Suspend a seeded firm → its staff get a "suspended" response on next
request and workers skip it; reactivate → access restored; extend trial → new expiry visible
to the firm; every action present in the audit log with old→new values.

**Acceptance Scenarios**:

1. **Given** an active firm, **When** the operator suspends it and confirms, **Then** the
   firm's staff receive a suspension response on their next request, scheduled work for the
   firm is skipped, and the action is audit-logged with old→new status.
2. **Given** a suspended firm, **When** reactivated, **Then** staff access resumes and the
   action is audit-logged.
3. **Given** a trial firm, **When** the operator extends the trial by X days, **Then** the
   new expiry is stored, visible on the dashboard, and audit-logged with old→new dates.
4. **Given** a firm on plan A, **When** the operator changes it to plan B and confirms,
   **Then** the subscription record reflects plan B with the change audit-logged. Plan
   changes here are administrative — they do not by themselves charge or refund money.
5. **Given** any lifecycle action, **When** the confirmation dialog is dismissed, **Then**
   nothing changes and nothing is logged as performed.
6. **Given** a cancelled firm, **When** the operator attempts to extend its trial, **Then**
   the action is rejected with a clear message (reactivate first).

---

### User Story 4 — Billing & Subscription Oversight (Priority: P2)

The operator reviews the billing state of the platform: each firm's subscription (plan,
provider, period end, status), the immutable billing-events inbox (webhook receipts), and a
queue of items needing attention — unprocessed events, failed or amount-mismatched payments.
For manual-provider firms (e.g., bank transfer), the operator can record a manual payment,
which activates the subscription period. The operator can mark a problem event as resolved
with a required note. Money movement itself (charges, refunds) happens in the payment
provider's own dashboard — this console records and reconciles, it does not move money.

**Why this priority**: Revenue assurance. P2 because Paymob's webhook flow already activates
firms automatically; this story covers the exceptions and the visibility.

**Independent Test**: Seed an unprocessed billing event and a manual-provider firm; verify
both appear in the attention queue; record a manual payment → subscription becomes active
and the action is audit-logged; resolve the event with a note → it leaves the queue, note
retained.

**Acceptance Scenarios**:

1. **Given** subscriptions across firms, **When** the operator opens billing oversight,
   **Then** each firm's plan, provider, period end, and status are listed.
2. **Given** a billing event received but never processed, **When** the queue loads, **Then**
   the event appears with its provider reference and received time; raw payload is viewable
   (it is the firm's own webhook data, not client work product).
3. **Given** a manual-provider firm with payment received off-platform, **When** the operator
   records the payment (amount, date, reference, note), **Then** the subscription period is
   activated, the firm flips to active, and the entry is audit-logged.
4. **Given** a problem event, **When** the operator marks it resolved, **Then** a note is
   required, the original event record is never altered (append-only inbox **[C-III]**), and
   the resolution is stored alongside it.

---

### User Story 5 — Platform Audit Log Viewer (Priority: P2)

The operator can search the platform-wide audit log: filter by firm, actor, entity type,
action, and date range. Operator actions themselves appear in the same log and are
distinguishable as platform-level actions. Audit entries are strictly read-only — there is
no edit, delete, or export-with-modification path. Secret values never appear **[C-III]**.

**Why this priority**: The audit log already exists and is append-only; this story is
visibility. P2 because SQL access covers emergencies today.

**Independent Test**: Perform a firm suspension (US3); find it in the viewer filtered by
firm and by operator-actor; verify entries cannot be modified and that a field-level old→new
diff is shown.

**Acceptance Scenarios**:

1. **Given** audit entries across firms, **When** filtered by one firm, **Then** only that
   firm's entries are shown — and the act of viewing them is itself logged as a cross-firm
   read.
2. **Given** an operator lifecycle action from US3, **When** the log is filtered by platform
   actions, **Then** the entry appears with who/when/what/old→new.
3. **Given** an audit entry whose change involved a secret (e.g., a firm's LLM key was set),
   **Then** the viewer shows action-only ("key changed by X at T"), never the value.
4. **Given** any attempt to alter or delete an audit entry through the console, **Then** no
   such capability exists in the interface and the underlying store rejects it.

---

### User Story 6 — Operational Health (Priority: P3)

The operator sees a health panel: background worker liveness (pipeline, scheduler — last
heartbeat time), each paying firm's WhatsApp session status (connected / disconnected /
not provisioned), and a recent-signups feed. From here the operator can spot a dead worker
or a dropped WhatsApp session before a firm reports it.

**Why this priority**: Valuable but observable today via container logs; ships last.

**Independent Test**: Stop the pipeline worker; the panel shows its heartbeat as stale
within the refresh interval. Disconnect a WAHA session; the firm's row shows disconnected.

**Acceptance Scenarios**:

1. **Given** running workers, **When** the panel loads, **Then** each worker shows a recent
   heartbeat; a heartbeat older than the threshold (default 5 minutes) is flagged stale.
2. **Given** a firm with a provisioned WhatsApp session, **When** the session drops, **Then**
   the panel reflects the disconnected state on next refresh.
3. **Given** the health panel, **Then** it is strictly read-only — restarts and
   re-provisioning remain host-level operations outside this console.

---

### Edge Cases

- **Operator account compromise suspected**: owner can revoke all operator sessions at once;
  lockout and revocation are themselves audit-logged.
- **Firm suspended mid-session**: firm staff with a live session receive the suspension
  response on their next request — suspension does not wait for token expiry.
- **Concurrent operator edits**: two operators changing the same firm — last write wins, both
  writes audit-logged; the dashboard reflects current state on refresh.
- **Webhook replay**: a billing event arriving twice (same provider reference) is absorbed by
  the inbox's idempotency; the duplicate never re-activates or double-counts.
- **Trial extension racing trial expiry**: an extension applied the same day the scheduler
  would suspend the firm must win if applied before the scheduler pass; afterwards, the
  operator reactivates explicitly.
- **No operator accounts exist** (fresh deployment): the console is inert; provisioning the
  first operator account is a deliberate deployment-time act, never a public signup path.
- **Missing operator context**: any console request lacking a valid operator identity returns
  nothing — fail-closed, mirroring **[C-I]** posture.

---

## Functional Requirements

### Access & Authentication

- **FR-301**: The system MUST provide a dedicated operator entry point, separate from firm
  login and the client portal. There MUST be no public signup path for operator accounts.
- **FR-302**: Operator authentication MUST require a second factor in addition to the
  credential.
- **FR-303**: Firm staff and client credentials MUST be rejected by every operator function,
  regardless of role; rejection attempts MUST be audit-logged.
- **FR-304**: Repeated failed operator logins MUST trigger temporary lockout (default: 5
  failures); lockouts MUST be audit-logged.
- **FR-305**: Operator sessions MUST expire after an idle timeout (default: 30 minutes) and
  MUST be individually and collectively revocable.
- **FR-306**: Operator account provisioning and deactivation MUST be a controlled action
  available only to the platform owner, and MUST be audit-logged.

### Cross-Firm Boundary

- **FR-310**: The operator surface MUST expose only operational metadata: firm records,
  subscription records, billing events, audit entries, usage **counts**, and health signals.
  It MUST NOT expose firm work product: case content, document content or names, contact
  identities, AI outputs, or firm-client billing details. **[C-I]**
- **FR-311**: Every cross-firm read of a specific firm's detail and every cross-firm write
  MUST produce an audit entry naming the operator, the firm, and the action. **[C-III]**
- **FR-312**: Operator access MUST be fail-closed: absent a valid operator identity, operator
  functions return nothing and reject writes.
- **FR-313**: The adversarial isolation test suite MUST be extended with operator checks: no
  firm credential reaches operator functions; operator metadata queries return no work
  product fields; fail-closed behavior holds. The suite MUST pass before release. **[C-I]**

### Firm Lifecycle

- **FR-320**: The operator MUST be able to suspend, reactivate, and cancel a firm; each
  action requires explicit confirmation and takes effect on the firm's next request.
- **FR-321**: The operator MUST be able to extend a firm's trial by a chosen number of days;
  extension of a cancelled firm MUST be rejected.
- **FR-322**: The operator MUST be able to change a firm's plan; the change is administrative
  and MUST NOT itself move money.
- **FR-323**: All lifecycle actions MUST be audit-logged with who/when/what and field-level
  old→new values. **[C-III]**
- **FR-324**: Suspension MUST also cause scheduled background work for that firm to be
  skipped (consistent with existing scheduler behavior).

### Billing Oversight

- **FR-330**: The operator MUST see all subscriptions with plan, provider, period end, and
  status, filterable by firm and status.
- **FR-331**: The operator MUST see the billing-events inbox including unprocessed events;
  the inbox remains append-only — no event record is ever edited or deleted.
- **FR-332**: The operator MUST be able to record a manual payment for a manual-provider
  firm (amount, date, reference, note), which activates the subscription period; the action
  MUST be audit-logged.
- **FR-333**: The operator MUST be able to mark a problem event resolved with a mandatory
  note, stored alongside (never inside) the original event.
- **FR-334**: The console MUST NOT initiate charges or refunds; money movement remains in
  the payment provider's own tooling.

### Audit Viewing

- **FR-340**: The operator MUST be able to filter the platform audit log by firm, actor,
  entity type, action, and date range, with field-level old→new diffs displayed.
- **FR-341**: Operator/platform actions MUST be distinguishable from firm-level actions in
  the log.
- **FR-342**: The viewer MUST be strictly read-only and MUST never display secret values
  (action-only entries for secret changes). **[C-III]**

### Operational Health

- **FR-350**: Background workers MUST emit heartbeats; the console MUST flag a worker whose
  heartbeat exceeds the staleness threshold (default 5 minutes).
- **FR-351**: The console MUST show each firm's WhatsApp session status (connected /
  disconnected / not provisioned), refreshed on view.
- **FR-352**: The health panel MUST be read-only; no restart/provision actions ship in this
  feature.

---

## Key Entities

- **Platform Operator Account** — a distinct account type for the SaaS operator; carries
  credential + second factor enrollment, active/locked state, and session set. Never linked
  to any firm.
- **Operator Session** — an authenticated operator context with idle expiry and revocation.
- **Firm** *(existing)* — gains no new fields conceptually; its status and trial expiry
  become operator-manageable.
- **Subscription** *(existing)* — plan/provider/period/status; operator-adjustable plan,
  manual-payment activation.
- **Billing Event** *(existing, append-only)* — gains an associated **Resolution Note**
  record (separate, references the event, never mutates it).
- **Manual Payment Record** — operator-recorded payment (amount, date, reference, note, firm,
  recorded-by) that activates a subscription period.
- **Audit Entry** *(existing, append-only)* — operator actions land here, distinguishable as
  platform-level.
- **Worker Heartbeat** — last-alive signal per background worker.

---

## Success Criteria

- **SC-1**: The operator can locate any firm and read its status, plan, and trial expiry in
  under 10 seconds from console open.
- **SC-2**: A firm suspension takes effect — staff blocked, scheduled work skipped — within
  60 seconds of confirmation.
- **SC-3**: 100% of operator actions (logins, lifecycle changes, manual payments, resolutions)
  appear in the audit log with who/when/what; verified by automated test.
- **SC-4**: 0 firm work-product fields are reachable through any operator function — verified
  by the extended isolation suite passing.
- **SC-5**: No firm credential of any role can invoke any operator function — verified by the
  extended isolation suite passing.
- **SC-6**: A stale worker or dropped WhatsApp session is visible on the health panel within
  5 minutes of occurrence.
- **SC-7**: Manual reconciliation of a payment (record → firm active) completes in under 2
  minutes of operator effort.

---

## Assumptions

1. **Operator team size**: a small, fixed set of operator accounts (initially one — the
   owner) with a single permission level. An operator role hierarchy (read-only auditor,
   support tier) is out of scope for this feature.
2. **Metadata-only boundary**: the operator never needs firm work product to run the
   platform; counts and platform records suffice. If a support case ever requires content
   access, that is a separate, explicitly-consented feature (not this one).
3. **Console language**: the operator console may be Arabic or bilingual; it is
   operator-facing, not firm-facing, so the firm-side RTL-Arabic mandate applies but is not
   client-visible. Default: same RTL Arabic UI as the rest of the platform.
4. **Manual reconciliation scope**: record-and-activate plus resolve-with-note. Refunds,
   dunning automation, and provider-side retries are out of scope.
5. **Health actions**: observability only; remediation (restart worker, re-provision WAHA
   session) stays at the host level for now.
6. **Account storage**: operator accounts live in the same identity system as the rest of
   the platform (one Supabase project — **[C-XII]**), distinguished by account type, never by
   firm membership.

## Out of Scope

- Impersonating a firm user or browsing a firm's workspace ("login as firm").
- Editing or deleting any firm data, documents, or AI outputs.
- Initiating charges or refunds.
- Operator role hierarchy / delegated admin.
- Automated dunning, payment retries, or trial-expiry email campaigns.
- Worker restart / WAHA session provisioning from the console.
