# WhatsApp (WAHA) Contract

**Plan**: [../plan.md](../plan.md)

The firm's **WAHA Plus session is the tenant identifier**; it is configured per instance in
`firm_settings` (`waha_url`, `waha_key` — secrets). Three flows use this channel: the
conversational assistant (inbound), reminders (outbound), and manager reports (outbound).

## Inbound — conversational assistant  (**[C-I]** isolation, FR-031/032, R12)

```text
WAHA webhook → backend
  1. Resolve sender phone → users row.
  2. Reject if no match OR user.status != active   → polite refusal, no case content.
  3. Scope retrieval to sender's role + case_assignments.
  4. Retriever (A): embed query → pgvector over [private + shared] → chunks.
  5. LLM (B): generate grounded answer with source links; persuasive-only framing for
     reference/precedent (istishhad), assistive-tool posture (**[C-VIII][C-IX]**).
  6. Any artifact meant for official use → created draft_unreviewed (**[C-II]**).
  7. Reply via WAHA; never reveal cases the sender is not assigned to.
```

Contract guarantees:
- Unregistered/inactive senders receive **0** case content.
- Answers are **grounded** (source links) and **scoped** to the caller's assignments.
- The assistant may be agentic (**[C-IV]** permits autonomy here) but still grounded + gated.

## Outbound — deadline/obligation reminders  (deterministic, **[C-IV]**, FR-023/024/025)

```text
Scheduler (C) fires (lead points 7d/3d/1d/same-day, firm-configurable)
  → query CONFIRMED deadlines/tasks (appeal types require confirmed=true)
  → for each due item: send WAHA message to responsible lawyer's verified phone
  → if unacknowledged near due date: also notify a partner_manager
  → write notifications_log (recipient, channel, scheduled_for, sent_at, status)
  → on send failure: status=failed, surfaced for follow-up (never silently dropped)
```

The LLM does **not** decide whether/whom to send; it may only phrase message prose.

## Outbound — manager daily reports  (deterministic, **[C-IV]**, FR-026/027)

```text
Scheduler (C) fires daily (firm local day boundary)
  → code selects events/tasks from stored, audited data:
        "what happened today" + "tomorrow's tasks"
  → LLM may phrase prose ONLY (cannot add/omit/select items)
  → send to manager(s) via WAHA → write reports_log
```

Contract guarantee: every report item reconciles to a stored, audited event (no AI-invented
items) — verifiable against the audit log (SC-009).

## Security
- WAHA URL/key are secrets in `firm_settings`; never logged as values.
- Webhook authenticated to the firm's session; messages never cross firm instances.
