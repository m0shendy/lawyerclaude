# Contracts — AI-Assisted Lawyer Office Management System

**Plan**: [../plan.md](../plan.md)

This feature exposes three external interface surfaces. Each is documented as a contract so the
implementation and tests can be written against it.

| Contract | File | Surface |
|---|---|---|
| REST API | [rest-api.md](rest-api.md) | FastAPI endpoints consumed by the Next.js dashboard (auth, CRUD, AI, review gate, deadlines, reports, settings, audit) |
| WhatsApp (WAHA) | [whatsapp.md](whatsapp.md) | Inbound assistant messages + outbound reminders/reports via the firm's WAHA session |
| UI screens | [ui-screens.md](ui-screens.md) | Screen → role → allowed actions contract (RBAC), incl. AI marking + review gate |

**Cross-cutting contract rules (apply to every surface):**

- Every create/update/delete writes an append-only `audit_log` entry (**[C-III]**).
- Every AI output is returned/created as `draft_unreviewed`, visibly AI-marked, with per-claim
  source links; export/print/attach/send is rejected until `approved` (**[C-II][C-V][C-VI]**).
- Role-based access is enforced server-side, not just in the UI (**[C-I]** in-instance RBAC).
- Secret values are never returned or logged; key changes are logged as action-only (**[C-III]**).
- Reference/risk outputs carry persuasive-only / not-prediction / assistive posture
  (**[C-VIII][C-IX]**).
