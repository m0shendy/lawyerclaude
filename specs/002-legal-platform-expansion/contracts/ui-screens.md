# UI Screen Contract: Legal Platform Expansion

**Date**: 2026-06-08
**Plan**: [../plan.md](../plan.md)
**Extends**: [spec 001 contracts/ui-screens.md](../../001-lawyer-office-management/contracts/ui-screens.md)

Role abbreviations: **PM** = partner_manager · **L** = lawyer · **PA** = paralegal ·
**S** = secretary · **C** = client (portal) · **–** = no access (route guard blocks).

Arabic RTL-first layout. All screens accessible to non-client roles live under the main
authenticated app. Client portal screens live under `/portal/**` (separate route group, role guard).

---

## Main App — New Screens

### Clients  `/app/clients`

| Screen | PM | L | PA | S | Actions |
|--------|-----|-----|-----|-----|---------|
| Client list | ✅ | ✅ | ✅ | ✅ | Search/filter, create, click to detail |
| Client detail | ✅ | ✅ | ✅ | ✅ | View profile, contacts, matters, invoices |
| Client create/edit | ✅ | ✅ | ✅ | ✅ | Form; auto-shows `client_number` on save |
| Conflict check panel | ✅ | ✅ | ✅ | ✅ | Appears inline during create/edit on opposing party entry; shows matches + notes |
| Contact management | ✅ | ✅ | ✅ | ✅ | Add/edit/remove typed contacts on client detail |

---

### Document Management  `/app/documents`  (within matter context)

| Screen | PM | L | PA | S | Actions |
|--------|-----|-----|-----|-----|---------|
| Document list (folder tree) | ✅ | ✅ | ✅ | ✅ | Folder nav, filter by access level / confidential |
| Document version history | ✅ | ✅ | ✅ | ✅ | View version chain, download any version |
| Check-out badge | ✅ | ✅ | ✅ | ✅ | Shows "Checked out by [name]" on locked docs; check-out/check-in buttons |
| Document access settings | ✅ | ✅ | – | – | Set access_level, toggle confidential flag |
| Client sharing panel | ✅ | ✅ | – | – | Add/remove client sharing; confidential docs blocked |
| Template library | ✅ | ✅ | ✅ | ✅ | Browse templates; create new from template |
| Template create/edit | ✅ | ✅ | – | – | Edit content_template with variable hints |

---

### Billing  `/app/billing`

| Screen | PM | L | PA | S | Actions |
|--------|-----|-----|-----|-----|---------|
| Invoice list | ✅ | ✅ | 👁 | 👁 | Filter by status/client/period; create new (PM, L only) |
| Invoice detail | ✅ | ✅ | 👁 | 👁 | View items, totals, payment history |
| Invoice create/edit | ✅ | ✅ | – | – | Add/remove line items; apply tax/discount; service catalog lookup |
| Record payment | ✅ | ✅ | – | – | Payment method, amount, date, reference |
| Service catalog | ✅ | ✅ | 👁 | 👁 | List default service items; manage (PM, L) |
| Financial summary | ✅ | ✅ | – | – | Revenue/outstanding totals at top of billing list |

(👁 = read-only)

---

### Hearings  `/app/hearings`

| Screen | PM | L | PA | S | Actions |
|--------|-----|-----|-----|-----|---------|
| Hearing list | ✅ | ✅ | ✅ | ✅ | Filter by matter/status/date; create |
| Hearing detail | ✅ | ✅ | ✅ | ✅ | View court info, docket, opposing counsel, reminder status |
| Hearing create/edit | ✅ | ✅ | ✅ | ✅ | Form; type dropdown (Egyptian civil court types) |
| Confirm hearing (lawyer ack.) | – | ✅ | – | – | "Confirm" button; sets `status=confirmed` |

---

### Appointments  `/app/appointments`

| Screen | PM | L | PA | S | Actions |
|--------|-----|-----|-----|-----|---------|
| Appointment list | ✅ | ✅ | ✅ | ✅ | Filter by lawyer/status/type/date |
| Appointment create/edit | ✅ | ✅ | ✅ | ✅ | Time slot picker; conflict warning inline |
| Conflict warning modal | ✅ | ✅ | ✅ | ✅ | Shown on attempted double-booking; must dismiss before saving |

---

### Calendar  `/app/calendar`

| Screen | PM | L | PA | S | Actions |
|--------|-----|-----|-----|-----|---------|
| Month view | ✅ | ✅ | ✅ | ✅ | Hearings + appointments; click event → quick-detail popover |
| Week view | ✅ | ✅ | ✅ | ✅ | Same events, time-of-day layout |
| Event type filter | ✅ | ✅ | ✅ | ✅ | All / Hearings / Appointments toggle |
| Quick-detail popover | ✅ | ✅ | ✅ | ✅ | Title, time, matter link, status; "Edit" → full detail |

---

### AI Document Features  (within matter context and standalone)

| Screen | PM | L | PA | S | Actions |
|--------|-----|-----|-----|-----|---------|
| Generate document | ✅ | ✅ | – | – | Choose type + template; AI generates; output appears as `draft_unreviewed` in AI outputs list |
| Contract review panel | ✅ | ✅ | – | – | Select document; trigger review; findings list with source links; each AI-marked |
| Letter pack generator | ✅ | ✅ | – | – | Choose template + matter; generates draft AI output |
| Case timeline view | ✅ | ✅ | 👁 | 👁 | Auto-generated timeline entries; each grounded to source; AI-marked until approved |
| Knowledge search | ✅ | ✅ | ✅ | ✅ | Natural language query; results from private + shared corpus; each result shows corpus source + persuasive label |
| AI output approval | ✅ | ✅* | – | – | "Reviewed & Approved" button on `draft_unreviewed` items; *L = only for matters assigned to them |

All AI outputs display **"AI-generated — requires review"** banner until `review_state = approved` **[C-VI]**.
Export/print/send controls are disabled on `draft_unreviewed` outputs **[C-II]**.

---

### Analytics  `/app/analytics` (PM only)

| Screen | PM | L | PA | S | Actions |
|--------|-----|-----|-----|-----|---------|
| Dashboard | ✅ | – | – | – | KPI cards (open matters, upcoming hearings, pending invoices, pending AI review) |
| Financial report | ✅ | – | – | – | Revenue by period, outstanding invoices, payment method chart |
| Operational report | ✅ | – | – | – | Workload by lawyer, matter resolution time distribution |
| Activity feed | ✅ | – | – | – | Recent audit log entries; filter by entity type / user |

Non-PM users receive `403` on any `/app/analytics/**` route.

---

### Extended Existing Screens

| Screen | Change |
|--------|--------|
| **Matter detail** | + client link (search select for `clients`), case_number auto-populated, practice area, court/jurisdiction, docket, tags, priority, stage fields |
| **Matter list** | + filter by client, practice area, stage, priority |
| **Dashboard** | + upcoming hearings card, pending invoices card (extends spec 001 dashboard) |
| **Settings** | + LLM provider config panel (provider dropdown, model, API key — masked); + client portal toggle |

---

## Client Portal — Screens  `/portal/**`

Route group gated to `role = client` JWT. Any non-client attempt → redirect to main login.
All portal screens are read-only unless noted. Arabic RTL layout same as main app.
"Assistive tool" disclaimer visible in portal footer on every screen **[C-VIII]**.

| Screen | Path | Actions |
|--------|------|---------|
| Portal dashboard | `/portal` | Overview: open matters, shared docs, pending invoices, upcoming consultations; AI insights (approved only) |
| Matters list | `/portal/matters` | Own matters (read-only); status, stage |
| Matter detail | `/portal/matters/:id` | Case info, shared documents, associated invoices |
| Documents | `/portal/documents` | Shared non-confidential docs; folder navigation; download |
| Invoices | `/portal/invoices` | Own invoices; status badges (draft hidden — only pending/partial/paid shown) |
| Invoice detail | `/portal/invoices/:id` | Line items, totals, payment history |
| Appointments | `/portal/appointments` | Upcoming consultations; status |
| AI insights | `/portal/insights` | Approved AI insights for own matters; each AI-marked **[C-VI]**; assistive-tool disclaimer **[C-VIII]** |
| Profile | `/portal/profile` | View + edit own contact info |

**Portal isolation rules** (enforced at both route and API level **[C-I]**):
- Client sees ONLY rows where `client_id = their own GoTrue uid`
- Confidential documents are never returned regardless of sharing
- `draft_unreviewed` AI outputs are never surfaced **[C-II]**
- Matter stages / internal notes / opposing counsel / audit log are not exposed

---

## Public Landing Page  `/` (unauthenticated)

| Element | Notes |
|---------|-------|
| Feature overview | Firm-facing marketing; no legal claims |
| "Request a demo" CTA | Opens contact form |
| **Assistive tool disclaimer** | Visible in footer: "هذا النظام أداة مساعدة للمحامين. المسؤولية المهنية تقع على عاتق المحامي." **[C-VIII]** |
| Sign-in button | Directs to GoTrue login for the firm's instance |
