# Per-Firm Backups + Restore Test (`infra/backup`) — [C-XI]

Constitution Principle XI: backups must be **tested for restore, not merely
taken**. An untested backup is not a backup.

> **THE RULE: no real firm is onboarded until a restore test has PASSED
> for that firm's backup pipeline.** (See quickstart.md §8.)

## Script

```bash
# Take a backup (db dump + storage tarball) and prune old ones:
./backup_restore_test.sh <firm-slug>

# Verify the LATEST dump actually restores (scratch container, then destroyed):
./backup_restore_test.sh <firm-slug> --restore-test
```

### Backup mode

- `pg_dump -Fc` of the firm database via the running `db` container
  → `/opt/backups/<slug>/<slug>-<UTC-timestamp>.dump`
- `tar.gz` of the firm's Storage data (uploaded documents)
  → `/opt/backups/<slug>/<slug>-<UTC-timestamp>-storage.tar.gz`
- Prunes files older than `RETENTION_DAYS` (default **14**; override via env).
- Backup dir is `chmod 700`, files created with umask 077 — dumps contain
  confidential legal data.

### Restore-test mode

1. Starts a **scratch** postgres container from the same image as the firm's
   db (so the postgres version and pgvector match), with no published ports.
2. `pg_restore`s the latest dump into it.
3. Verifies:
   - critical tables exist, **including `audit_log`** [C-III];
   - `SELECT count(*)` works on critical tables (data pages restored);
   - append-only audit survived: an `UPDATE` on `audit_log` as `app_user`
     is **rejected** (the REVOKE round-tripped through dump/restore).
4. Destroys the scratch container (also on interrupt/failure, via trap).
5. Prints `RESULT: PASS` / `RESULT: FAIL`; exits non-zero on FAIL.

## Cron schedule (per firm, on the host)

Add to root's crontab (`sudo crontab -e`), one pair of lines per firm —
note the off-hour minutes to avoid load spikes:

```cron
# Daily backup at 02:17 host time
17 2 * * *  /opt/lawyerclaude/infra/backup/backup_restore_test.sh alfarouk >> /var/log/backup-alfarouk.log 2>&1

# Weekly restore test, Sundays at 03:41 — FAIL must page the operator
41 3 * * 0  /opt/lawyerclaude/infra/backup/backup_restore_test.sh alfarouk --restore-test >> /var/log/backup-alfarouk.log 2>&1 || echo "RESTORE TEST FAILED: alfarouk" | logger -p user.crit -t backup
```

Adjust the repo path (`/opt/lawyerclaude`) to where the repository is checked
out on the host. Wire the failure branch into whatever alerting you have
(mail, ntfy, Uptime-Kuma push) — a failed restore test is an **incident**.

## Off-host copies

`/opt/backups` on the same disk protects against `docker compose down -v`
and operator error, not against disk loss. Sync `/opt/backups/<slug>/` to an
encrypted off-host target (restic/rclone/borg) as a follow-up hardening step;
the restore test above remains the proof either way.
