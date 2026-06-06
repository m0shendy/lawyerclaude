#!/usr/bin/env bash
#
# backup_restore_test.sh — Per-firm automated backup, and the restore test
# that makes it an actual backup.  [C-XI]
#
# Usage:
#   ./backup_restore_test.sh <firm-slug>                 # take a backup + prune
#   ./backup_restore_test.sh <firm-slug> --restore-test  # verify the latest dump restores
#
# Backup mode:
#   - pg_dump -Fc (custom format) of the firm database via the running db
#     container  -> /opt/backups/<slug>/<slug>-<UTC timestamp>.dump
#   - tar.gz of the firm's Storage data (uploaded documents)
#     -> /opt/backups/<slug>/<slug>-<UTC timestamp>-storage.tar.gz
#   - prunes backups older than RETENTION_DAYS (default 14).
#
# Restore-test mode (constitution Principle XI: backups must be TESTED for
# restore, not merely taken):
#   - starts a scratch postgres container from the SAME image as the firm db,
#   - pg_restore's the latest dump into it,
#   - verifies: critical tables exist (incl. audit_log), row counts readable,
#     and audit_log append-only is preserved (UPDATE as app_user must FAIL),
#   - destroys the scratch container, prints PASS/FAIL, exits non-zero on FAIL.
#
# RULE: no real firm is onboarded until a restore test has PASSED.
#
# Environment overrides:
#   FIRMS_ROOT      (default /opt/firms)
#   BACKUP_ROOT     (default /opt/backups)
#   RETENTION_DAYS  (default 14)

set -euo pipefail

FIRMS_ROOT="${FIRMS_ROOT:-/opt/firms}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

usage() {
  echo "Usage: $(basename "$0") <firm-slug> [--restore-test]" >&2
  exit 64
}

[[ $# -ge 1 && $# -le 2 ]] || usage
FIRM_SLUG="$1"
MODE="${2:-backup}"
[[ "$FIRM_SLUG" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || usage
[[ "$MODE" == "backup" || "$MODE" == "--restore-test" ]] || usage

FIRM_DIR="${FIRMS_ROOT}/${FIRM_SLUG}"
BACKUP_DIR="${BACKUP_ROOT}/${FIRM_SLUG}"

log()  { printf '\033[1;34m[backup:%s]\033[0m %s\n' "$FIRM_SLUG" "$*"; }
err()  { printf '\033[1;31m[backup:%s] ERROR:\033[0m %s\n' "$FIRM_SLUG" "$*" >&2; }
die()  { err "$*"; exit 1; }

[[ -d "$FIRM_DIR" ]] || die "firm directory not found: ${FIRM_DIR}"
command -v docker >/dev/null || die "docker is not installed"

compose() { ( cd "$FIRM_DIR" && docker compose -p "$FIRM_SLUG" "$@" ); }

# ==========================================================================
# BACKUP MODE
# ==========================================================================

do_backup() {
  local ts dump_file storage_file
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  dump_file="${BACKUP_DIR}/${FIRM_SLUG}-${ts}.dump"
  storage_file="${BACKUP_DIR}/${FIRM_SLUG}-${ts}-storage.tar.gz"

  # Backups contain confidential legal data — keep the directory private.
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"

  # ---- 1. Database dump (custom format → pg_restore-able, compressed) ----
  log "Dumping database -> ${dump_file}"
  ( umask 077 && : > "$dump_file" )
  compose exec -T db pg_dump -U postgres -d postgres -Fc > "$dump_file"
  [[ -s "$dump_file" ]] || die "database dump is empty"
  log "Database dump done ($(du -h "$dump_file" | cut -f1))"

  # ---- 2. Storage volume tarball (uploaded documents) --------------------
  # The storage service persists either to a bind mount under the firm dir
  # (volumes/storage) or to a named compose volume (<slug>_storage-data).
  # Handle both; warn (not fail) if neither exists yet — a brand-new firm
  # may simply have no uploads.
  local bind_dir="${FIRM_DIR}/volumes/storage"
  local named_vol="${FIRM_SLUG}_storage-data"

  if [[ -d "$bind_dir" ]]; then
    log "Archiving storage bind mount -> ${storage_file}"
    ( umask 077 && tar -czf "$storage_file" -C "$bind_dir" . )
  elif docker volume inspect "$named_vol" >/dev/null 2>&1; then
    log "Archiving named volume ${named_vol} -> ${storage_file}"
    ( umask 077 && : > "$storage_file" )
    # Read-only mount of the volume inside a throwaway container; tar to stdout.
    docker run --rm -v "${named_vol}:/data:ro" alpine \
      tar -czf - -C /data . > "$storage_file"
  else
    err "no storage data found (neither ${bind_dir} nor volume ${named_vol}) — skipping storage archive"
    storage_file="(none)"
  fi

  # ---- 3. Prune old backups ----------------------------------------------
  log "Pruning backups older than ${RETENTION_DAYS} days"
  find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name "${FIRM_SLUG}-*.dump" -o -name "${FIRM_SLUG}-*-storage.tar.gz" \) \
    -mtime "+${RETENTION_DAYS}" -print -delete | sed 's/^/    pruned: /' || true

  log "Backup complete:"
  log "  db:      ${dump_file}"
  log "  storage: ${storage_file}"
  log "Remember [C-XI]: a backup only counts once '$(basename "$0") ${FIRM_SLUG} --restore-test' PASSES."
}

# ==========================================================================
# RESTORE-TEST MODE
# ==========================================================================

do_restore_test() {
  local latest_dump scratch db_image failures=0

  # ---- locate the latest dump --------------------------------------------
  latest_dump="$(ls -1t "${BACKUP_DIR}/${FIRM_SLUG}-"*.dump 2>/dev/null | head -n1 || true)"
  [[ -n "$latest_dump" ]] || die "no dumps found in ${BACKUP_DIR} — run a backup first"
  log "Restore-testing latest dump: ${latest_dump}"

  # ---- use the SAME postgres image as the firm's db ----------------------
  # so extensions (pgvector) and version match exactly.
  db_image="$(compose images db --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | head -n1 || true)"
  if [[ -z "$db_image" || "$db_image" == *"<none>"* ]]; then
    # Fallback: inspect the running container.
    db_image="$(docker inspect --format '{{.Config.Image}}' \
                  "$(compose ps -q db)" 2>/dev/null || true)"
  fi
  [[ -n "$db_image" ]] || die "could not determine the firm db image (is the stack up?)"
  log "Scratch postgres image: ${db_image}"

  # ---- spin up the scratch container --------------------------------------
  scratch="restore-test-${FIRM_SLUG}-$$"
  # Always clean up the scratch container, even on failure/interrupt.
  cleanup() { docker rm -f "$scratch" >/dev/null 2>&1 || true; }
  trap cleanup EXIT

  log "Starting scratch container ${scratch} (no published ports, isolated)"
  docker run -d --name "$scratch" \
    -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
    -e POSTGRES_DB=postgres \
    "$db_image" >/dev/null

  log "Waiting for scratch postgres to accept connections"
  local deadline=$(( $(date +%s) + 120 ))
  until docker exec "$scratch" pg_isready -U postgres -d postgres >/dev/null 2>&1; do
    (( $(date +%s) < deadline )) || die "scratch postgres did not start within 120s"
    sleep 2
  done

  # ---- restore -------------------------------------------------------------
  # --no-owner/--no-privileges keep the restore independent of host roles…
  # except roles we explicitly need: create app_user first so the GRANT/REVOKE
  # verification below is meaningful.
  log "Creating app_user role in scratch (NOLOGIN is fine for SET ROLE checks)"
  docker exec "$scratch" psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
    -c "CREATE ROLE app_user;" >/dev/null

  # Restore into a FRESH database, not the image's pre-initialized 'postgres' DB.
  # The supabase/postgres image pre-creates the auth/storage schemas in 'postgres',
  # which collide with the dump ("schema auth already exists"). A brand-new DB
  # from template1 has none of those, so the dump restores cleanly.
  local rdb="restoretest"
  log "Creating fresh scratch database '${rdb}' for an isolated restore"
  docker exec "$scratch" psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
    -c "CREATE DATABASE ${rdb};" >/dev/null

  # Skip Supabase-internal, extension-managed schemas (vault/pgsodium): in the
  # image, 'postgres' is not a true superuser and is denied COPY into e.g.
  # vault.secrets. Those hold no application data (the app keeps secrets in
  # public.firm_settings) and are recreated by a fresh stack on real restore. We
  # validate the APPLICATION schemas (public/auth/storage) via a filtered TOC so
  # the full backup stays faithful while the test restores cleanly.
  log "Restoring dump (pg_restore; vault/pgsodium internals filtered)"
  docker cp "$latest_dump" "${scratch}:/tmp/firm.dump" >/dev/null
  docker exec "$scratch" sh -c \
    "pg_restore -l /tmp/firm.dump | grep -viE 'vault|pgsodium' > /tmp/firm.toc"
  if ! docker exec "$scratch" pg_restore -U postgres -d "$rdb" \
         --no-owner --exit-on-error -L /tmp/firm.toc /tmp/firm.dump; then
    err "pg_restore FAILED"
    echo "RESULT: FAIL — dump did not restore cleanly."
    exit 1
  fi

  # ---- verification ---------------------------------------------------------
  psql_scratch() { docker exec -i "$scratch" psql -U postgres -d "$rdb" -tA -v ON_ERROR_STOP=1 -c "$1"; }

  echo
  echo "Verification:"

  # 1. Critical tables exist (audit_log is non-negotiable [C-III]).
  local critical_tables=(audit_log users cases documents ai_outputs deadlines firm_settings)
  for tbl in "${critical_tables[@]}"; do
    if [[ "$(psql_scratch "SELECT to_regclass('public.${tbl}') IS NOT NULL;")" == "t" ]]; then
      echo "  ✓ table exists: ${tbl}"
    else
      echo "  ✗ MISSING table: ${tbl}"
      failures=$((failures + 1))
    fi
  done

  # 2. Row counts are readable from critical tables (proves data pages restored).
  for tbl in audit_log users cases documents; do
    if count="$(psql_scratch "SELECT count(*) FROM public.${tbl};" 2>/dev/null)"; then
      echo "  ✓ SELECT count(*) FROM ${tbl} -> ${count}"
    else
      echo "  ✗ cannot count rows in ${tbl}"
      failures=$((failures + 1))
    fi
  done

  # 3. Append-only audit_log survived the round trip [C-III]:
  #    as app_user, an UPDATE on audit_log MUST be rejected
  #    (the migrations REVOKE UPDATE, DELETE from app_user).
  #    We EXPECT this command to fail — failure here is the PASS condition.
  if docker exec "$scratch" psql -U postgres -d "$rdb" -v ON_ERROR_STOP=1 -c \
       "SET ROLE app_user; UPDATE public.audit_log SET action = action WHERE false;" \
       >/dev/null 2>&1; then
    echo "  ✗ audit_log UPDATE as app_user SUCCEEDED — append-only REVOKE was lost in restore!"
    failures=$((failures + 1))
  else
    echo "  ✓ audit_log UPDATE as app_user rejected (append-only preserved)"
  fi

  # ---- summary ---------------------------------------------------------------
  echo
  if (( failures > 0 )); then
    echo "RESULT: FAIL — ${failures} verification(s) failed for ${latest_dump}"
    echo "Do NOT trust this backup. Do NOT onboard a real firm on this pipeline. [C-XI]"
    exit 1
  fi
  echo "RESULT: PASS — ${latest_dump} restores cleanly; audit_log append-only intact. [C-XI]"
  # trap destroys the scratch container on exit.
}

# ==========================================================================
case "$MODE" in
  backup)         do_backup ;;
  --restore-test) do_restore_test ;;
esac
