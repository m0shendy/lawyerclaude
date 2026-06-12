# REST API Contract: Legal Platform Expansion

**Date**: 2026-06-08
**Plan**: [../plan.md](../plan.md)
**Extends**: [spec 001 contracts/rest-api.md](../../001-lawyer-office-management/contracts/rest-api.md)

All endpoints require a valid Bearer JWT from Supabase GoTrue unless noted as `PUBLIC`.
Role abbreviations: **PM** = partner_manager · **L** = lawyer · **PA** = paralegal ·
**S** = secretary · **C** = client (portal). Format: `HTTP METHOD /path — roles — description`.

---

## Client Management  `/api/v1/clients`

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `GET /clients` | PM, L, PA, S | List/search clients; supports `?q=` full-text, `?type=`, `?status=` |
| `POST /clients` | PM, L, PA, S | Create client; auto-generates `client_number` |
| `GET /clients/:id` | PM, L, PA, S | Get client record + contacts |
| `PATCH /clients/:id` | PM, L, PA, S | Update client fields; audit-logged |
| `DELETE /clients/:id` | PM | Soft-delete (sets `status=inactive`); audit-logged |
| `GET /clients/:id/contacts` | PM, L, PA, S | List typed contacts |
| `POST /clients/:id/contacts` | PM, L, PA, S | Add contact |
| `PATCH /clients/:id/contacts/:cid` | PM, L, PA, S | Update contact |
| `DELETE /clients/:id/contacts/:cid` | PM, L | Delete contact; audit-logged |
| `POST /clients/conflict-check` | PM, L, PA, S | `{ party_name }` → conflict check; logs to `conflict_check_log`; returns matches + notes |

---

## Document Management System  `/api/v1/documents`  `/api/v1/folders`

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `GET /folders?matter_id=` | PM, L, PA, S | List folder tree for matter |
| `POST /folders` | PM, L, PA, S | Create folder; `{ matter_id, name, parent_folder_id? }` |
| `PATCH /folders/:id` | PM, L | Rename folder |
| `DELETE /folders/:id` | PM | Delete empty folder |
| `GET /documents/:id/versions` | PM, L, PA, S | List version chain for document |
| `GET /documents/:id/versions/:vid` | PM, L, PA, S | Get specific version metadata + download URL |
| `POST /documents/:id/checkout` | PM, L, PA, S | Check out document; 409 if already checked out by another user |
| `DELETE /documents/:id/checkout` | PM, L, PA, S | Check in (discard checkout without new version) |
| `POST /documents/:id/checkin` | PM, L, PA, S | Check in with new version: multipart file upload; creates `document_versions` row |
| `PATCH /documents/:id/access` | PM, L | Set `access_level` and `is_confidential` |
| `POST /documents/:id/share` | PM, L | Share document with client: `{ client_id }` |
| `DELETE /documents/:id/share/:client_id` | PM, L | Revoke client sharing |
| `GET /templates` | PM, L, PA, S | List document templates; `?category=` filter |
| `POST /templates` | PM, L | Create template |
| `PATCH /templates/:id` | PM, L | Update template |
| `DELETE /templates/:id` | PM | Delete template |
| `POST /templates/:id/generate` | PM, L | Generate draft from template + matter context; returns `ai_outputs` id (doc_draft or letter_pack) |

---

## Billing & Invoicing  `/api/v1/invoices`  `/api/v1/service-catalog`

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `GET /invoices` | PM, L, PA, S | List invoices; `?client_id=`, `?status=`, `?matter_id=` |
| `POST /invoices` | PM, L | Create invoice; auto-generates `invoice_number`; status = `draft` |
| `GET /invoices/:id` | PM, L, PA, S | Invoice + line items + payments |
| `PATCH /invoices/:id` | PM, L | Update invoice (only while `draft`); audit-logged |
| `POST /invoices/:id/issue` | PM, L | Transition `draft → pending`; audit-logged |
| `POST /invoices/:id/cancel` | PM, L | Cancel invoice; audit-logged |
| `GET /invoices/:id/items` | PM, L, PA, S | List line items |
| `POST /invoices/:id/items` | PM, L | Add line item; recalculates totals |
| `PATCH /invoices/:id/items/:iid` | PM, L | Update line item |
| `DELETE /invoices/:id/items/:iid` | PM, L | Remove line item |
| `POST /invoices/:id/payments` | PM, L | Record payment `{ method, amount, payment_date, reference? }` |
| `GET /invoices/:id/payments` | PM, L, PA, S | List payments for invoice |
| `GET /service-catalog` | PM, L, PA, S | List service items |
| `POST /service-catalog` | PM, L | Create service item |
| `PATCH /service-catalog/:id` | PM, L | Update service item |
| `DELETE /service-catalog/:id` | PM | Delete service item |

---

## Hearing Management  `/api/v1/hearings`

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `GET /hearings` | PM, L, PA, S | List; `?matter_id=`, `?status=`, `?from=`, `?to=` |
| `POST /hearings` | PM, L, PA, S | Create hearing linked to matter |
| `GET /hearings/:id` | PM, L, PA, S | Get hearing details |
| `PATCH /hearings/:id` | PM, L, PA, S | Update; audit-logged |
| `DELETE /hearings/:id` | PM, L | Soft-cancel (sets `status=cancelled`); audit-logged |
| `POST /hearings/:id/confirm` | L, PM | Lawyer acknowledges hearing (sets `status=confirmed`) |

---

## Appointment Scheduling  `/api/v1/appointments`

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `GET /appointments` | PM, L, PA, S | List; `?lawyer_id=`, `?status=`, `?from=`, `?to=` |
| `POST /appointments` | PM, L, PA, S | Create appointment; API checks time-slot conflict for `assigned_lawyer_id`; 409 on conflict |
| `GET /appointments/:id` | PM, L, PA, S | Get appointment details |
| `PATCH /appointments/:id` | PM, L, PA, S | Update/reschedule; re-runs conflict check; audit-logged |
| `DELETE /appointments/:id` | PM, L | Cancel appointment; audit-logged |

---

## Calendar  `/api/v1/calendar`

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `GET /calendar` | PM, L, PA, S | Query `calendar_events` view; `?from=`, `?to=`, `?type=hearing\|appointment\|all`, `?lawyer_id=` |

---

## AI Document Features  `/api/v1/ai`

All AI endpoints: output is created as `ai_outputs` row with `review_state=draft_unreviewed`,
AI-marked, source links required. Approver = assigned lawyer or PM only **[C-II][C-V][C-VI]**.

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `POST /ai/draft-document` | PM, L | Generate doc draft: `{ matter_id, doc_type, template_id?, context? }` → `ai_outputs` (type=`doc_draft`) |
| `POST /ai/contract-review` | PM, L | Review contract: `{ document_id, playbook_id? }` → `ai_outputs` (type=`clause_flag` + `analysis`) |
| `POST /ai/letter-pack` | PM, L | Generate letter: `{ matter_id, template_id, context? }` → `ai_outputs` (type=`letter_pack`) |
| `POST /ai/case-timeline` | PM, L | Generate timeline: `{ matter_id }` → `ai_outputs` (type=`case_timeline`) |
| `GET /ai/knowledge-search` | PM, L, PA, S | Natural language search: `?q=`, `?corpus=private\|shared\|all` → results with source links + persuasive framing **[C-IX]** |
| `POST /ai/outputs/:id/approve` | PM, L | Approve output; caller must be assigned lawyer on matter or PM; sets `review_state=approved`, records `approved_by/at` **[C-II]** |

---

## Client Portal  `/api/v1/portal` (role = `client` only)

All portal endpoints reject non-`client` JWT claims. RLS restricts rows to `client_id = auth.uid()`.

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `GET /portal/matters` | C | List own matters (read-only view) |
| `GET /portal/matters/:id` | C | Get matter details (read-only) |
| `GET /portal/documents` | C | List shared non-confidential documents for own matters |
| `GET /portal/documents/:id/download` | C | Download shared document (Storage pre-signed URL) |
| `GET /portal/invoices` | C | List own invoices |
| `GET /portal/invoices/:id` | C | Invoice details + payments |
| `GET /portal/appointments` | C | Upcoming consultations |
| `GET /portal/ai-insights` | C | Approved AI insights (review_state=`approved`) for own matters |
| `GET /portal/profile` | C | Own client profile |
| `PATCH /portal/profile` | C | Update own profile; audit-logged |

---

## Analytics & Reporting  `/api/v1/analytics` (role = `partner_manager` only)

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `GET /analytics/dashboard` | PM | KPIs from `dashboard_kpis` materialized view |
| `GET /analytics/financial` | PM | Revenue by period, outstanding invoices, payment method breakdown; `?from=&to=` |
| `GET /analytics/operational` | PM | Workload by lawyer, matter resolution time distribution |
| `GET /analytics/activity-feed` | PM | Recent `audit_log` entries; `?limit=`, `?offset=` |

---

## LLM Provider Configuration (extends Settings)

| Endpoint | Roles | Notes |
|----------|-------|-------|
| `PATCH /settings/llm-provider` | PM | `{ provider, model, api_key }` — stored in `firm_settings.llm_provider_config`; key is secret, audit-logged as action-only **[C-III]** |
| `POST /settings/llm-provider/test` | PM | Sends a test prompt to verify the configured provider; does not produce an `ai_outputs` row |

---

## Error responses

All endpoints return standard JSON error envelopes:

```json
{ "error": "<code>", "message": "<human-readable>", "detail": {} }
```

Key error codes for new endpoints:
- `document_already_checked_out` (409) — check-out attempt on locked document
- `appointment_time_conflict` (409) — booking a conflicting time slot
- `invoice_not_editable` (422) — attempting to edit a non-draft invoice
- `ai_output_not_approved` (403) — attempting to export/send a draft_unreviewed output
- `conflict_check_match` (200 + `conflicts: []`) — not an error; warning surfaced in response body
- `confidential_document` (403) — portal client attempting to access a confidential document
