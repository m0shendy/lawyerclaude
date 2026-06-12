# Quickstart: Legal Platform Expansion

**Date**: 2026-06-08
**Plan**: [plan.md](plan.md)
**Prereq**: A working firm instance from [spec 001 quickstart.md](../001-lawyer-office-management/quickstart.md).

This guide walks through an end-to-end smoke-test of all expansion features on a single
firm instance (demo/home environment, dummy data only). Steps are ordered to respect
dependencies. Expected time: ~30 minutes for first run.

---

## 0. Prerequisites

```bash
# Confirm spec 001 baseline is healthy
curl https://<firm>.local/api/v1/health          # expects 200
# Apply expansion migration
psql $DATABASE_URL < supabase/migrations/0017_expansion.sql
# Verify new tables exist
psql $DATABASE_URL -c "\dt clients"
psql $DATABASE_URL -c "\dt invoices"
psql $DATABASE_URL -c "\dt hearings"
```

---

## 1. Configure multi-provider LLM

```bash
# As partner_manager — set provider to Gemini (or your test key)
curl -X PATCH https://<firm>.local/api/v1/settings/llm-provider \
  -H "Authorization: Bearer $PM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "provider": "gemini", "model": "models/gemini-2.0-flash", "api_key": "<TEST_KEY>" }'
# Expected: 200; audit_log records action=llm_provider_updated (key NOT in log)

# Test connectivity
curl -X POST https://<firm>.local/api/v1/settings/llm-provider/test \
  -H "Authorization: Bearer $PM_TOKEN"
# Expected: 200 { "status": "ok", "provider": "gemini" }
```

---

## 2. Create a client with conflict check

```bash
# Create first client
curl -X POST https://<firm>.local/api/v1/clients \
  -H "Authorization: Bearer $L_TOKEN" \
  -d '{ "name": "شركة النيل للتجارة", "type": "organization" }'
# Expected: 201 { "client_number": "CL-000001", … }

# Add an opposing contact
curl -X POST https://<firm>.local/api/v1/clients/$CLIENT_ID/contacts \
  -d '{ "contact_type": "opposing", "name": "محمد عبد الله", "phone": "+201001234567" }'

# Now create a second client with the same opposing party — should trigger conflict
curl -X POST https://<firm>.local/api/v1/clients/conflict-check \
  -d '{ "party_name": "محمد عبد الله" }'
# Expected: 200 { "result": "conflict_found", "conflicts": [{ "matter_id": …, "party": "…" }] }
# Verify conflict_check_log has a new row
```

---

## 3. Link client to a matter and verify extended matter fields

```bash
# Create matter with new fields
curl -X POST https://<firm>.local/api/v1/cases \
  -d '{
    "title": "قضية عقد تجاري",
    "client_id": "'$CLIENT_ID'",
    "practice_area": "commercial",
    "court": "محكمة القاهرة الاقتصادية",
    "priority": "high",
    "stage": "active"
  }'
# Expected: 201 { "case_number": "CASE-0001", … }
```

---

## 4. Document version control and check-in/out

```bash
# Upload initial document (creates document row in spec 001 pipeline)
# … assume DOC_ID is the ID of a ready document

# Check out
curl -X POST https://<firm>.local/api/v1/documents/$DOC_ID/checkout \
  -H "Authorization: Bearer $L_TOKEN"
# Expected: 201

# Try to check out from a second user — must fail
curl -X POST https://<firm>.local/api/v1/documents/$DOC_ID/checkout \
  -H "Authorization: Bearer $L2_TOKEN"
# Expected: 409 { "error": "document_already_checked_out" }

# Check in with new version (upload a revised PDF)
curl -X POST https://<firm>.local/api/v1/documents/$DOC_ID/checkin \
  -F "file=@revised.pdf"
# Expected: 201; document_versions has 2 rows; checkout row deleted; audit_log has doc_checkin

# Verify version chain
curl https://<firm>.local/api/v1/documents/$DOC_ID/versions
# Expected: [{ version_number: 1, … }, { version_number: 2, … }]
```

---

## 5. AI document drafting (review gate enforced)

```bash
# Generate a contract draft
curl -X POST https://<firm>.local/api/v1/ai/draft-document \
  -H "Authorization: Bearer $L_TOKEN" \
  -d '{ "matter_id": "'$MATTER_ID'", "doc_type": "contract" }'
# Expected: 201 { "ai_output_id": "…", "review_state": "draft_unreviewed" }

# Verify: attempt to export — must be blocked
curl https://<firm>.local/api/v1/ai/outputs/$AI_ID/export
# Expected: 403 { "error": "ai_output_not_approved" }

# Approve it
curl -X POST https://<firm>.local/api/v1/ai/outputs/$AI_ID/approve \
  -H "Authorization: Bearer $L_TOKEN"
# Expected: 200; review_state = approved; audit_log has approval event
# Now export works:
curl https://<firm>.local/api/v1/ai/outputs/$AI_ID/export
# Expected: 200 (PDF download)
```

---

## 6. Billing: create invoice, record payment

```bash
# Create invoice
curl -X POST https://<firm>.local/api/v1/invoices \
  -H "Authorization: Bearer $L_TOKEN" \
  -d '{ "client_id": "'$CLIENT_ID'", "matter_id": "'$MATTER_ID'", "tax_rate": 14 }'
# Expected: 201 { "invoice_number": "INV-202606-000001", "status": "draft" }

# Add line items
curl -X POST https://<firm>.local/api/v1/invoices/$INV_ID/items \
  -d '{ "description": "رسوم استشارة قانونية", "quantity": 1, "unit_price": 5000 }'

# Issue invoice (draft → pending)
curl -X POST https://<firm>.local/api/v1/invoices/$INV_ID/issue
# Expected: 200 { "status": "pending" }; audit_log records invoice_status_changed

# Record partial payment
curl -X POST https://<firm>.local/api/v1/invoices/$INV_ID/payments \
  -d '{ "method": "bank_transfer", "amount": 3000, "payment_date": "2026-06-08" }'
# Expected: 201; invoice status → partial; audit_log records payment_recorded
```

---

## 7. Create a hearing and verify reminder scheduling

```bash
# Create hearing 3 days from now
curl -X POST https://<firm>.local/api/v1/hearings \
  -d '{
    "matter_id": "'$MATTER_ID'",
    "type": "murafa_a",
    "court_name": "محكمة القاهرة الاقتصادية",
    "judge": "القاضي محمود علي",
    "scheduled_at": "'$(date -d '+3 days' -Iseconds)'",
    "assigned_lawyer_id": "'$LAWYER_ID'",
    "reminder_days": 3
  }'
# Expected: 201; hearing in calendar_events view

# Manually trigger scheduler (test mode)
curl -X POST https://<firm>.local/api/v1/internal/scheduler/run-hearing-reminders \
  -H "X-Internal-Key: $SCHEDULER_KEY"
# Expected: notifications_log has new row; WAHA notification sent to lawyer's phone
```

---

## 8. Appointment booking with conflict detection

```bash
# Book appointment
curl -X POST https://<firm>.local/api/v1/appointments \
  -d '{ "type": "consultation", "assigned_lawyer_id": "'$LAWYER_ID'",
        "client_id": "'$CLIENT_ID'", "scheduled_at": "2026-06-10T10:00:00+02:00",
        "duration_minutes": 60 }'
# Expected: 201

# Attempt a conflicting booking (same lawyer, overlapping time)
curl -X POST https://<firm>.local/api/v1/appointments \
  -d '{ "type": "follow_up", "assigned_lawyer_id": "'$LAWYER_ID'",
        "scheduled_at": "2026-06-10T10:30:00+02:00", "duration_minutes": 60 }'
# Expected: 409 { "error": "appointment_time_conflict" }

# Verify both appear correctly in calendar
curl "https://<firm>.local/api/v1/calendar?from=2026-06-10&to=2026-06-11"
# Expected: array with 1 appointment event
```

---

## 9. Client portal end-to-end

```bash
# Admin creates a client portal user
curl -X POST https://<firm>.local/api/v1/users \
  -H "Authorization: Bearer $PM_TOKEN" \
  -d '{ "email": "client@example.com", "role": "client",
        "client_id": "'$CLIENT_ID'", "full_name": "محمد الزبون" }'

# Share a non-confidential document with the client
curl -X POST https://<firm>.local/api/v1/documents/$DOC_ID/share \
  -H "Authorization: Bearer $L_TOKEN" \
  -d '{ "client_id": "'$CLIENT_ID'" }'

# Client logs in and fetches portal data
C_TOKEN=$(curl -X POST https://<firm>.local/auth/v1/token?grant_type=password \
  -d '{"email":"client@example.com","password":"<pw>"}' | jq -r .access_token)

curl https://<firm>.local/api/v1/portal/matters -H "Authorization: Bearer $C_TOKEN"
# Expected: own matters only

curl https://<firm>.local/api/v1/portal/documents -H "Authorization: Bearer $C_TOKEN"
# Expected: only the shared non-confidential document

curl https://<firm>.local/api/v1/portal/invoices -H "Authorization: Bearer $C_TOKEN"
# Expected: own invoices (pending/partial/paid — no drafts)

# Verify client CANNOT access another client's matter
curl "https://<firm>.local/api/v1/portal/matters/$OTHER_MATTER_ID" \
  -H "Authorization: Bearer $C_TOKEN"
# Expected: 403 or 404 (RLS hides the row)
```

---

## 10. Analytics dashboard

```bash
# Refresh materialized view (normally triggered automatically)
curl -X POST https://<firm>.local/api/v1/internal/analytics/refresh \
  -H "X-Internal-Key: $SCHEDULER_KEY"

# Fetch KPIs as PM
curl https://<firm>.local/api/v1/analytics/dashboard \
  -H "Authorization: Bearer $PM_TOKEN"
# Expected: { open_matters: 1, upcoming_hearings: 1, pending_invoices: 1,
#              upcoming_deadlines: 0, pending_review: 1 }
# Reconcile each figure against the data created in steps 3–8.

# Non-PM must be rejected
curl https://<firm>.local/api/v1/analytics/dashboard \
  -H "Authorization: Bearer $L_TOKEN"
# Expected: 403
```

---

## 11. Verify audit log completeness

```bash
# Check that all operations above produced audit entries
psql $DATABASE_URL -c "
  SELECT action, entity, created_at
  FROM audit_log
  WHERE created_at > now() - interval '1 hour'
  ORDER BY created_at DESC
  LIMIT 30;
"
# Expected entries (non-exhaustive):
#   llm_provider_updated, client_created, conflict_check_run,
#   case_created, doc_checkout, doc_checkin, ai_output_created,
#   ai_output_approved, invoice_created, invoice_status_changed,
#   payment_recorded, hearing_created, appointment_created,
#   doc_shared, portal_profile_viewed
```

---

## Completion criteria

All of the following must be true before marking this phase production-ready:

- [ ] Multi-provider LLM config switches without code change; key never appears in audit_log
- [ ] Conflict check returns matches on known-conflicting parties; logged
- [ ] Case numbers (CASE-XXXX), client numbers (CL-XXXXXX), invoice numbers (INV-YYYYMM-XXXXXX) auto-generate without collision under concurrent inserts
- [ ] Document check-out is exclusive (409 on double check-out)
- [ ] Version chain is intact after check-in; prior versions downloadable
- [ ] All AI outputs born `draft_unreviewed`; export blocked until approved; AI marking visible
- [ ] Invoice lifecycle (draft→pending→partial→paid) and payment recording audit-logged
- [ ] Hearing reminder fires via deterministic scheduler; logged in notifications_log
- [ ] Appointment conflict detection prevents double-booking (409)
- [ ] Calendar view returns both hearings and appointments in correct time range
- [ ] Portal client sees only own data; cross-client and cross-firm access denied
- [ ] `draft_unreviewed` AI outputs not visible in portal
- [ ] Analytics KPIs reconcile to created records; blocked for non-PM
- [ ] Every operation above produced an audit_log entry; no gaps
