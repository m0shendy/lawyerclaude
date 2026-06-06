# Operations Notes — Provisioning & Performance (T102, T103)

## Provisioning hardening for repeatability (T102) [C-XI]

`infra/provision/provision_firm.sh` works for the first firms; harden it before
scaling past ~3–4 instances. Known gaps to address (tracked; see
`MEMORY: repo-infra-gaps`):

- **Idempotency:** re-running for an existing slug should be safe (detect an
  existing stack and refuse or `--force` cleanly) rather than half-applying.
- **Secret generation:** generate and persist FRESH per-firm secrets in one place
  (`secrets/`), never reuse across firms, never echo to logs. [C-III][C-XI]
- **Migration gating:** apply `supabase/migrations/0001..NNNN` in order and fail
  fast on any error before building app images (already partly done — verify).
- **Build-before-up:** build backend+frontend before `up -d` so a broken build
  never leaves a firm half-started (already done — keep).
- **Health gating:** wait on `db` healthy + migrations before starting workers.
- **Restore-test gate:** do not mark a firm "ready for onboarding" until
  `backup_restore_test.sh <slug> --restore-test` PASSES (see
  `infra/backup/RESTORE_TEST.md` — currently blocked).

Until hardened, treat provisioning as a guided manual procedure
(`infra/DEPLOYMENT_RUNBOOK.md`), not a fire-and-forget script.

## Performance pass (T103)

Confirm these hold as data grows (defaults in `backend/app/core/config.py`):

- **OCR + embedding are async/background.** Document intake runs in the pipeline
  worker (`backend/workers/pipeline_worker.py`), never inline in a request —
  uploads return immediately with status `pending`/`processing`. Verify no
  endpoint blocks on Document AI or embedding calls.
- **Retrieval latency.** pgvector HNSW cosine index (`0003_vector_index.sql`)
  backs `document_chunks`/`reference_chunks`. `top_k=8` per corpus. Watch query
  latency as chunk counts grow; tune HNSW `ef_search` / index params if needed.
- **LLM calls are per-request and gated.** Summarize/analyze/risk/assistant each
  make one generation call; they are user-triggered, not batch. The scheduler
  (reminders/reports) makes at most one phrasing call per section per day.
- **Connection pools.** API uses the RLS `app_user` pool (max 10); workers use
  the BYPASSRLS service pool (max 5). Revisit sizes under concurrent firms.

No code changes required from this pass for current scale; revisit at the
documented checkpoints when onboarding more firms or larger corpora.
