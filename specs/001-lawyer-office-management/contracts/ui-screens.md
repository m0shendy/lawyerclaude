# UI Screens Contract (RTL Arabic dashboard)

**Plan**: [../plan.md](../plan.md)

Next.js 14 dashboard, RTL-first Arabic. Each screen declares the roles that may access it and the
actions allowed. A persistent **"assistive tool — not legal advice"** disclaimer is present
(**[C-VIII]**). Every create/update/delete writes an `audit_log` entry. AI content always renders
via the shared `<AiMarkedOutput/>` (banner + source links) and respects the review gate.

| Screen | Roles | Key actions / contract |
|---|---|---|
| **Login** | all | Supabase GoTrue; per-instance users only; inactive users rejected |
| **Dashboard** | all (role-aware) | upcoming deadlines, documents in `processing`, items awaiting review, today's tasks |
| **Cases list** | all (scoped) | view assigned/firm cases |
| **Case detail** | assigned/manager | CRUD case; assign/unassign lawyers; shows documents, AI outputs, deadlines, tasks |
| **Document upload + status** | all | upload (→ `pending`); lifecycle status; `low_confidence` shows warning banner (**[C-VII]**) |
| **AI output review** | view: assigned/manager · approve: **assigned lawyer or manager** | AI-marked content (**[C-VI]**) + source links (**[C-V]**); "Reviewed & Approved" button; export/send disabled until approved (**[C-II]**); paralegal/secretary cannot approve |
| **Deadlines** | assigned/manager | list/detail; general CRUD; appeal deadlines shown as **confirm-required suggestions** with "Verify & Confirm"; appeal UI hidden unless `feature_appeal_deadlines` on (**[C-X]**) |
| **Tasks** | manager, lawyer, paralegal | CRUD + assign + due dates |
| **Conversational assistant** | all (scoped) | chat (in-app + WhatsApp); grounded; scoped to caller's cases; outputs gated |
| **Reports** | **manager only** | daily "what happened" + "tomorrow's tasks" |
| **Settings / Admin** | **manager only** | enter WAHA URL/key, LLM API key, embedding config, firm profile; secrets masked; key add/edit audited as action+who, not value (**[C-III]**) |
| **Users & roles** | **manager only** | CRUD users; assign roles; activate/deactivate |
| **Audit log viewer** | **manager only** | **read-only** change history |

**Shared components (contract-level):**
- `<AiMarkedOutput/>` — renders the "AI-generated — requires review" banner, source links, and
  the heightened warning when `low_confidence_flag` is set; hides export/send until `approved`.
- `<Disclaimer/>` — persistent assistive-tool / not-legal-advice notice.
- `<ReviewGate/>` — wraps any export/print/attach/send affordance; enabled only when `approved`.
