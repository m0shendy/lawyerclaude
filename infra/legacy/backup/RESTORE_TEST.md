# Backup Restore Test — Results & Findings (T101) [C-XI]

Constitution Principle XI: *a backup only counts once it has been **restore-tested**.*
This records the first executed restore test for the `lawyer` firm and its
findings.

## Run

- **Date:** 2026-06-06
- **Firm:** `lawyer` (192.168.5.61)
- **Dump:** `/opt/backups/lawyer/lawyer-20260606T110914Z.dump` (392K, `pg_dump -Fc`)
- **Procedure:** `infra/backup/backup_restore_test.sh lawyer --restore-test`
  (scratch `supabase/postgres:15.8.1.085` container, isolated, no published ports).

## Result: ⚠️ FAIL — logical restore is not clean (backup data is intact, restore path is not)

The dump **contains** the data (it is a faithful `pg_dump`), but a naive
`pg_restore` of a full self-hosted **Supabase** database does not replay cleanly.
The test surfaced three layered issues; the first two are fixed in the script,
the third is a backup-strategy decision:

1. **`schema "auth" already exists`** — the scratch image pre-creates Supabase
   schemas in the default `postgres` DB. **Fixed:** restore into a fresh
   `restoretest` database (template1, empty).
2. **`permission denied for table vault.secrets`** — in the image `postgres` is
   not a true superuser. `vault`/`pgsodium` are Supabase-internal (no app data;
   the app keeps secrets in `public.firm_settings`). **Fixed:** restore via a
   filtered TOC that skips `vault`/`pgsodium`.
3. **`terminating connection ... increment_schema_version()`** — a Supabase
   event trigger (schema-version / PostgREST DDL-reload `NOTIFY`) fires during
   restore and kills the session. **Not yet resolved** — needs a deliberate fix.

## Why #3 is a strategy decision (surfaced for sign-off)

Self-hosted Supabase ships event triggers/functions that are hostile to logical
replay. The robust options, in order of preference:

- **A. Physical backups / PITR** (WAL archiving or a volume/snapshot of the `db`
  data dir). Restores the cluster exactly — sidesteps every logical-replay quirk.
  Recommended for production legal data.
- **B. Scoped logical dump** — back up only application data (`public` + selected
  `auth`/`storage` tables incl. `auth.users`) and restore into a *freshly
  provisioned* Supabase stack (which already has the managed schemas/triggers).
  Lighter, but must be proven to capture everything needed.
- **C. Full logical dump restored as `supabase_admin`** with event triggers
  disabled (`ALTER EVENT TRIGGER ... DISABLE`) around the restore. Requires the
  superuser credential, which the scratch test does not currently have.

## Status / gate

Per **C-XI**, **no real firm is onboarded until a restore test PASSES.** The
`lawyer` instance currently has tested, *intact* dumps but an unproven restore
path — treat backups as **not yet trustworthy for DR** until option A/B/C is
chosen, implemented, and this test re-run to **PASS**.

## Script improvements landed in this run

`backup_restore_test.sh` now: restores into a fresh DB (#1) and filters
`vault`/`pgsodium` internals (#2). Re-run after deciding the strategy above.
