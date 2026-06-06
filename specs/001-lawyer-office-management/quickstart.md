# Quickstart: Provision a Firm Instance & Run a Document End-to-End

**Plan**: [plan.md](plan.md)

This is the operator path to stand up one isolated firm instance and validate the spine
(isolation → upload → OCR → confidence gate → normalize → embed → review gate). Demo and
production run the **same** Docker stack; this works on the home server (dummy data) and the VPS.

## 0. Prerequisites
- Docker + docker-compose, Portainer, Traefik with wildcard DNS + wildcard Let's Encrypt TLS.
- Google Document AI processor (Enterprise Document OCR) credentials.
- A WAHA Plus session (Sumopod) for this firm.
- The shared Egyptian-law corpus available (central read-only service, or baked-in). **Public law
  only.**

## 1. Provision the firm instance (`infra/provision`)
1. Run the per-firm provisioning script with the firm slug/subdomain.
2. It generates **fresh** secrets (new GoTrue/JWT secrets — never defaults, **[C-XI]**).
3. Brings up the firm's Supabase stack (Postgres + pgvector, GoTrue, Storage) + backend + frontend.
4. Registers `firmslug.<domain>` → the firm container in Traefik (wildcard TLS).
5. Restricts Supabase Studio (network-restricted + auth), enables host firewall.
6. Configures the WAHA session for this firm.

## 2. Apply schema & RLS
- Run `supabase/migrations` (schema, pgvector + HNSW index, in-instance RLS roles, **audit
  triggers**, review-gate guards). Confirm `audit_log` is INSERT-only (no update/delete).

## 3. Seed the firm (DEMO ONLY uses dummy data — never real client docs)
- Create one user per role; set verified phone numbers.
- Set `firm_settings`: WAHA URL/key, LLM API key, embedding config, reminder lead points.
- Leave `feature_appeal_deadlines = false` (**[C-X]**).

## 4. Smoke-test isolation & audit  (**[C-I][C-III]**)
- Log in as each role; confirm manager-only screens are blocked for non-managers.
- Confirm a user from another firm instance cannot authenticate here.
- Make any edit; confirm an `audit_log` row captured who/role/when/old→new and cannot be deleted.

## 5. Run a document through the pipeline  (the spine)
1. Upload a PDF to a case → row `pending`.
2. Worker: pre-process → Document AI → **confidence gate** → Arabic normalization → chunk →
   embed → `document_chunks` → status `ready` (or `low_confidence` / `failed`).
3. **CHECKPOINT (Phase 1):** run this on a **real sample of the firm's actual scans** and inspect
   `ocr_confidence`. STOP and review the threshold before building further — this number gates
   every downstream output (**[C-VII]**).

## 6. Validate the review gate  (**[C-II][C-V][C-VI]**)
1. Summarize the `ready` document → an `ai_output` is created `draft_unreviewed`, AI-marked, with
   per-claim source links.
2. Attempt export/send → **blocked**.
3. As the **assigned lawyer or a manager**, click "Reviewed & Approved" → state `approved`,
   approver + version recorded; export now allowed. As paralegal/secretary → approval denied.
4. If the document was `low_confidence`, confirm the heightened warning appears.

## 7. Validate notifications (deterministic)  (**[C-IV]**)
- Create a confirmed deadline with a responsible lawyer + near-future due date.
- Trigger the scheduler; confirm a WhatsApp reminder is sent and `notifications_log` is written;
  confirm partner escalation when unacknowledged.

## 8. Backups before any real firm  (**[C-XI]**)
- Enable per-firm automated backups; **perform a test restore** into a scratch stack and verify
  data integrity. Do **not** onboard a real firm until restore is proven.

## 9. Promote home → VPS (lift-and-shift)
- Because home holds only dummy data, promotion is a **deployment**, not a live-data migration:
  deploy the same compose on the VPS, generate fresh prod secrets, point DNS at the VPS, enable
  wildcard SSL + backups, smoke-test with dummy data, then onboard the first real firm.
