# Phase 1 Data Model: AI-Assisted Lawyer Office Management System

**Date**: 2026-06-05
**Plan**: [plan.md](plan.md) · **Spec**: [spec.md](spec.md)

Scope: the schema for **one firm instance** (each firm has its own copy). Exact column types are
finalized in-build; entities, relationships, RLS intent, audit behavior, and state machines below
are binding. All tables except `audit_log` and the read-only shared corpus are **audited** (R6)
and **RLS-protected by in-instance role** (not cross-firm — that is the instance boundary, **[C-I]**).

## Roles

`partner_manager` (manager) · `lawyer` · `paralegal` · `secretary`. Manager-only surfaces:
Reports, Settings/Admin, Users & Roles, Audit Log viewer.

## Entities

### firm_settings  *(one row per instance — holds secrets)*
| Field | Notes |
|---|---|
| id | singleton |
| firm_name, locale | profile (locale RTL Arabic default) |
| waha_url, waha_key | WhatsApp; **secret** — never logged as value (**[C-III]**) |
| llm_api_key | client-provided; **secret** |
| embedding_config | model + dimension (R1) |
| reminder_lead_points | JSON, default 7d/3d/1d/same-day (R9) |
| feature_appeal_deadlines | bool, default **false** (**[C-X]**, R10) |
| subscription_metadata | plan info |

### users  *(auth via Supabase GoTrue; this row holds profile + role)*
id · full_name · email · **phone (verified)** · **role** · status (`active`|`inactive`).
Rule: assistant/reminders use `phone`; only `active` users authenticate or are answered (R12).

### cases (matters)
id · title · client_name · case_number · court · case_type · status · created_by · created_at.

### case_assignments  *(many-to-many users↔cases)*
id · case_id → cases · user_id → users. Drives "notify responsible lawyer" and report scope.

### documents
id · case_id → cases · file_path (Storage) · source_type (`text_pdf`|`scanned`) ·
**status** (`pending`→`processing`→`ready`|`low_confidence`|`failed`) · ocr_confidence ·
uploaded_by · uploaded_at.

### document_chunks
id · document_id → documents · chunk_text (normalized Arabic, R5) ·
**embedding `vector(N)`** (pgvector, HNSW/cosine, R2) · page_ref/source_location (grounding, **[C-V]**).

### ai_outputs
id · (document_id and/or case_id) · type (`summary`|`extraction`|`analysis`|`clause_flag`|`risk_signal`) ·
content · **source_links** (→ chunks, grounding) · **review_state** (`draft_unreviewed`|`approved`,
default `draft_unreviewed`) · low_confidence_flag · generated_by_model · created_at ·
approved_by · approved_at · approved_version.
Rules: **[C-II]** born `draft_unreviewed`; export/print/attach/send require `approved`;
approver ∈ {assigned lawyer on the case, any partner_manager} (FR-018).

### deadlines
id · case_id → cases · type (`general`|`appeal_istinaf`|`mu'arada`|`naqd`) · basis ·
suggested_date · **confirmed** (bool) · confirmed_by · confirmed_at · responsible_user_id → users ·
derived_from_document_id → documents · low_confidence_flag.
Rules: appeal types are **suggestions** (`confirmed=false`), gated by `feature_appeal_deadlines`,
inert until "Verified & Confirmed" (**[C-X]**, FR-028/029/030).

### tasks
id · case_id → cases · assigned_to → users · description · due_date · status.

### notifications_log
id · (deadline_id|task_id) · recipient_user_id → users · channel (`whatsapp`) · scheduled_for ·
sent_at · status (`sent`|`failed`|`skipped`). Proof a reminder fired; failures recorded, never
silently dropped (FR-025).

### reports_log
id · type (`daily_what_happened`|`tomorrow_tasks`) · recipient_user_id → users · generated_at · sent_at.

### references_private
Firm's own uploaded references; chunked + embedded like documents (private corpus).

### shared corpus  *(read-only, public law only — central or baked-in, R11)*
Egyptian public-law reference base. **No firm/client data ever written** (**[C-I]**). Not audited
(read-only, non-instance data).

### audit_log  *(append-only — written by DB triggers, R6)*
id · who_user_id · who_role · when_ts · entity_table · record_id · action (`create`|`update`|`delete`) ·
change_detail (field-level old→new JSON; secrets redacted) · context (screen/endpoint).
Rules: **[C-III]** append-only (`REVOKE UPDATE, DELETE`); secrets logged as "changed" not value;
AI approvals + deadline confirmations captured with version.

## Relationships

```text
firm_settings (1) ── (∞) users
users (∞) ── (∞) cases                via case_assignments
cases (1) ── (∞) documents
documents (1) ── (∞) document_chunks  (chunk holds embedding + source ref)
documents/cases (1) ── (∞) ai_outputs (source_links → chunks  = grounding)
cases (1) ── (∞) deadlines ── (1) responsible user
cases (1) ── (∞) tasks ── (1) assigned user
deadlines/tasks (1) ── (∞) notifications_log
every mutation on every audited table ── (1) audit_log entry (via trigger)
```

## State machines

**documents.status**
```text
pending → processing → ready
                     → low_confidence   (ocr_confidence < threshold, R4 — heightened warning downstream)
                     → failed           (hard OCR/processor error — surfaced to user, no AI output)
```

**ai_outputs.review_state**  (**[C-II]**)
```text
draft_unreviewed ──(assigned lawyer | partner clicks "Reviewed & Approved")──▶ approved
   │  export/print/attach/send  → BLOCKED while draft_unreviewed
   └─ low_confidence_flag=true  → heightened warning, may require double review (**[C-VII]**)
```

**deadlines (appeal types).confirmed**  (**[C-X]**)
```text
suggested (confirmed=false, no notifications, behind feature flag)
   ──(responsible lawyer clicks "Verified & Confirmed")──▶ confirmed=true → reminders schedule
```

## Validation & integrity rules

- `ai_outputs.review_state` default `draft_unreviewed`; transition to `approved` only by an
  assigned lawyer or partner; export/send queries filter `review_state = 'approved'` (R7).
- Appeal-type deadlines cannot schedule notifications unless `confirmed = true` **and**
  `feature_appeal_deadlines = true`.
- Outputs derived from a `low_confidence` document set `low_confidence_flag = true`.
- `notifications_log` written for every send attempt (incl. `failed`/`skipped`).
- Shared corpus is read-only; no write path from firm data.
- Secret columns (`waha_key`, `llm_api_key`) redacted in audit diffs.
- `audit_log` is append-only: app DB roles hold INSERT only.
