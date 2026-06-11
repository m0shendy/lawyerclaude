#!/usr/bin/env bash
#
# provision_firm.sh — Provision one fully isolated firm instance.  [C-XI]
#
# Usage:
#   ./provision_firm.sh <firm-slug> <base-domain>
#
# Example:
#   ./provision_firm.sh alfarouk example-legal.com
#   → https://alfarouk.example-legal.com (dashboard)
#   → https://api.alfarouk.example-legal.com (backend API)
#
# What it does (constitution Principle I — per-firm physical isolation,
# Principle XI — self-hosting security baseline):
#   1. Validates the firm slug and creates /opt/firms/<slug>/.
#   2. Generates FRESH secrets — never defaults: Postgres superuser password,
#      GoTrue JWT secret, app_user DB password, and derives the Supabase
#      ANON_KEY / SERVICE_ROLE_KEY as HS256 JWTs signed with the fresh secret.
#   3. Renders .env (chmod 600) and kong.yml from the repo templates.
#   4. Brings the firm stack up (compose project name = firm slug) and waits
#      for the database to become healthy.
#   5. Applies every supabase/migrations/*.sql in lexical order.
#   6. Prints a summary with URLs, secret locations and the remaining manual
#      steps (WAHA session, LLM key, Studio SSH-tunnel access).
#
# Prerequisites (see README.md in this directory):
#   - Linux Docker host with docker compose v2.
#   - Traefik already running on the external `proxy` network with wildcard
#     DNS + wildcard Let's Encrypt TLS for <base-domain>.
#   - This repository checked out on the host (script paths are repo-relative).
#
# This script is idempotent-ish: re-running for an existing slug REFUSES to
# overwrite an existing .env (so fresh secrets are generated exactly once and
# never silently rotated, which would orphan issued JWTs).

set -euo pipefail

# --------------------------------------------------------------------------
# Constants & arguments
# --------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

FIRMS_ROOT="${FIRMS_ROOT:-/opt/firms}"          # override for testing
DB_WAIT_TIMEOUT="${DB_WAIT_TIMEOUT:-180}"        # seconds to wait for healthy db

usage() {
  echo "Usage: $(basename "$0") <firm-slug> <base-domain>" >&2
  echo "  firm-slug   : lowercase letters, digits and dashes only (e.g. alfarouk)" >&2
  echo "  base-domain : the wildcard-routed base domain (e.g. example-legal.com)" >&2
  exit 64
}

[[ $# -eq 2 ]] || usage

FIRM_SLUG="$1"
BASE_DOMAIN="$2"

log()  { printf '\033[1;34m[provision]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[provision] ERROR:\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# --------------------------------------------------------------------------
# 1. Validate inputs and prepare the firm directory
# --------------------------------------------------------------------------

# Slug becomes: subdomain, compose project name, docker volume prefix and the
# directory name — keep the charset strict so it is valid in all of them.
[[ "$FIRM_SLUG" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] \
  || die "invalid firm slug '${FIRM_SLUG}' — allowed: [a-z0-9-], must start/end alphanumeric"

[[ "$BASE_DOMAIN" =~ ^[a-z0-9.-]+\.[a-z]{2,}$ ]] \
  || die "invalid base domain '${BASE_DOMAIN}'"

command -v docker  >/dev/null || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "docker compose v2 is not available"
command -v openssl >/dev/null || die "openssl is not installed"
command -v envsubst >/dev/null || die "envsubst is not installed (apt install gettext-base)"

FIRM_DIR="${FIRMS_ROOT}/${FIRM_SLUG}"
ENV_FILE="${FIRM_DIR}/.env"

if [[ -f "$ENV_FILE" ]]; then
  die ".env already exists at ${ENV_FILE} — refusing to regenerate secrets for an existing firm.
      To re-provision from scratch: docker compose -p ${FIRM_SLUG} down -v && rm -rf ${FIRM_DIR}"
fi

log "Creating firm directory ${FIRM_DIR}"
mkdir -p "$FIRM_DIR"

# Copy the per-firm compose file and the volumes template (kong config,
# db init scripts, etc.) into the firm directory so each firm is fully
# self-contained and upgrades are explicit per firm.
COMPOSE_SRC="${REPO_ROOT}/infra/docker-compose.yml"
[[ -f "$COMPOSE_SRC" ]] || die "missing ${COMPOSE_SRC} — author the per-firm stack first (task T004)"
cp "$COMPOSE_SRC" "${FIRM_DIR}/docker-compose.yml"

if [[ -d "${REPO_ROOT}/infra/volumes-template" ]]; then
  log "Copying volumes template (kong/db/storage config)"
  cp -r "${REPO_ROOT}/infra/volumes-template" "${FIRM_DIR}/volumes"
else
  mkdir -p "${FIRM_DIR}/volumes/api" "${FIRM_DIR}/volumes/db" "${FIRM_DIR}/volumes/storage"
fi
mkdir -p "${FIRM_DIR}/volumes/db" "${FIRM_DIR}/volumes/storage"

# docker-compose mounts ./secrets/google-credentials.json into backend/worker
# containers. Create an empty placeholder so compose does not auto-create a
# DIRECTORY at that path; the operator replaces it with the real Document AI
# service-account JSON (chmod 600) before enabling live OCR intake.
mkdir -p "${FIRM_DIR}/secrets"
if [[ ! -f "${FIRM_DIR}/secrets/google-credentials.json" ]]; then
  ( umask 077 && printf '{}\n' > "${FIRM_DIR}/secrets/google-credentials.json" )
fi

# --------------------------------------------------------------------------
# 2. Generate FRESH secrets — never defaults  [C-XI]
# --------------------------------------------------------------------------

log "Generating fresh secrets (openssl rand)"

POSTGRES_PASSWORD="$(openssl rand -hex 24)"   # db superuser
JWT_SECRET="$(openssl rand -hex 32)"          # GoTrue / PostgREST / Kong HS256 secret
APP_USER_PASSWORD="$(openssl rand -hex 24)"   # backend app role (set after migrations)
DASHBOARD_PASSWORD="$(openssl rand -hex 16)"  # Supabase Studio basic-auth password

# ---- minimal pure-bash HS256 JWT signer (header.payload.signature) --------
# base64url: standard base64 with '+/' -> '-_' and padding stripped.
b64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

# sign_jwt <role> — emits a JWT with the Supabase-conventional claims
# { role, iss: "supabase", iat, exp(+10y) } signed HS256 with $JWT_SECRET.
sign_jwt() {
  local role="$1"
  local now exp header payload signature
  now="$(date +%s)"
  exp=$(( now + 10 * 365 * 24 * 3600 ))   # 10 years

  header="$(printf '{"alg":"HS256","typ":"JWT"}' | b64url)"
  payload="$(printf '{"role":"%s","iss":"supabase","iat":%d,"exp":%d}' \
              "$role" "$now" "$exp" | b64url)"
  signature="$(printf '%s.%s' "$header" "$payload" \
              | openssl dgst -sha256 -hmac "$JWT_SECRET" -binary | b64url)"

  printf '%s.%s.%s' "$header" "$payload" "$signature"
}

ANON_KEY="$(sign_jwt anon)"
SERVICE_ROLE_KEY="$(sign_jwt service_role)"

# --------------------------------------------------------------------------
# 3. Render .env from the template (chmod 600)
# --------------------------------------------------------------------------

# Template lives next to this script per IMPLEMENTATION_CONVENTIONS.md, with a
# fallback to infra/env.template for older layouts.
ENV_TEMPLATE=""
for candidate in "${SCRIPT_DIR}/env.template" "${REPO_ROOT}/infra/env.template"; do
  [[ -f "$candidate" ]] && { ENV_TEMPLATE="$candidate"; break; }
done
[[ -n "$ENV_TEMPLATE" ]] || die "env template not found (looked for infra/provision/env.template and infra/env.template)"

log "Rendering .env from ${ENV_TEMPLATE}"

# Absolute build contexts for the app images. The compose file is copied into
# ${FIRM_DIR}, so a relative '../backend' would resolve outside the repo; pin
# them to the checked-out repo so `docker compose build` works from anywhere.
BACKEND_CONTEXT="${REPO_ROOT}/backend"
FRONTEND_CONTEXT="${REPO_ROOT}/frontend"

# Export exactly the variables the template may reference, then envsubst with
# an explicit allowlist so any other '$' in the template passes through intact.
export FIRM_SLUG BASE_DOMAIN \
       POSTGRES_PASSWORD JWT_SECRET ANON_KEY SERVICE_ROLE_KEY \
       APP_USER_PASSWORD DASHBOARD_PASSWORD \
       BACKEND_CONTEXT FRONTEND_CONTEXT

# Older Bash-friendly umask dance: create the file private BEFORE writing
# secrets into it, so there is no window where it is world-readable.
( umask 077 && : > "$ENV_FILE" )
envsubst '${FIRM_SLUG} ${BASE_DOMAIN} ${POSTGRES_PASSWORD} ${JWT_SECRET} ${ANON_KEY} ${SERVICE_ROLE_KEY} ${APP_USER_PASSWORD} ${DASHBOARD_PASSWORD} ${BACKEND_CONTEXT} ${FRONTEND_CONTEXT}' \
  < "$ENV_TEMPLATE" > "$ENV_FILE"
chmod 600 "$ENV_FILE"

# --------------------------------------------------------------------------
# 4. Render kong.yml with the generated keys
# --------------------------------------------------------------------------

# Kong's declarative config embeds the anon / service_role keys as key-auth
# consumer credentials; it must be rendered per firm with the fresh keys.
KONG_TEMPLATE=""
for candidate in \
  "${REPO_ROOT}/infra/volumes-template/api/kong.yml" \
  "${FIRM_DIR}/volumes/api/kong.template.yml" \
  "${REPO_ROOT}/infra/volumes/api/kong.template.yml" \
  "${REPO_ROOT}/infra/kong.template.yml"; do
  [[ -f "$candidate" ]] && { KONG_TEMPLATE="$candidate"; break; }
done

if [[ -n "$KONG_TEMPLATE" ]]; then
  log "Rendering kong.yml from ${KONG_TEMPLATE}"
  mkdir -p "${FIRM_DIR}/volumes/api"
  ( umask 077 && : > "${FIRM_DIR}/volumes/api/kong.yml" )
  envsubst '${ANON_KEY} ${SERVICE_ROLE_KEY} ${DASHBOARD_PASSWORD}' \
    < "$KONG_TEMPLATE" > "${FIRM_DIR}/volumes/api/kong.yml"
  # Kong runs as uid 100 and must READ this file. Prefer owning it to uid 100 so
  # it stays non-world-readable (chmod 640); if we can't chown (no root), fall
  # back to 0644 so Kong can still read it.
  chmod 640 "${FIRM_DIR}/volumes/api/kong.yml"
  if ! sudo -n chown 100:100 "${FIRM_DIR}/volumes/api/kong.yml" 2>/dev/null; then
    chmod 644 "${FIRM_DIR}/volumes/api/kong.yml"
  fi
else
  err "kong template not found — if the stack mounts volumes/api/kong.yml, create it before 'up'"
fi

# --------------------------------------------------------------------------
# 5. Bring up the CORE Supabase services and wait for the database
# --------------------------------------------------------------------------
# Only prebuilt-image services start here. The app images (backend / workers /
# frontend) are built and started AFTER migrations (step 7) so a slow or broken
# app build can never block the database from being provisioned and migrated.

CORE_SERVICES="db auth rest storage kong meta studio"
log "Starting core services: ${CORE_SERVICES}"
( cd "$FIRM_DIR" && docker compose -p "$FIRM_SLUG" up -d ${CORE_SERVICES} )

log "Waiting for the database to become healthy (timeout ${DB_WAIT_TIMEOUT}s)"
deadline=$(( $(date +%s) + DB_WAIT_TIMEOUT ))
until ( cd "$FIRM_DIR" && docker compose -p "$FIRM_SLUG" exec -T db \
          pg_isready -U postgres -d postgres >/dev/null 2>&1 ); do
  if (( $(date +%s) >= deadline )); then
    err "database did not become ready within ${DB_WAIT_TIMEOUT}s"
    ( cd "$FIRM_DIR" && docker compose -p "$FIRM_SLUG" logs --tail 50 db ) || true
    exit 1
  fi
  sleep 3
done
log "Database is ready."

# --------------------------------------------------------------------------
# 6. Apply migrations in lexical order
# --------------------------------------------------------------------------

MIGRATIONS_DIR="${REPO_ROOT}/supabase/migrations"
[[ -d "$MIGRATIONS_DIR" ]] || die "migrations directory not found: ${MIGRATIONS_DIR}"

shopt -s nullglob
migrations=( "${MIGRATIONS_DIR}"/*.sql )
shopt -u nullglob
(( ${#migrations[@]} > 0 )) || die "no .sql migrations found in ${MIGRATIONS_DIR}"

# Glob order is lexical, which matches the 0001_…, 0002_… naming convention.
for migration in "${migrations[@]}"; do
  log "Applying migration: $(basename "$migration")"
  ( cd "$FIRM_DIR" && docker compose -p "$FIRM_SLUG" exec -T db \
      psql -U postgres -d postgres -v ON_ERROR_STOP=1 ) < "$migration"
done

# Migrations create role app_user without a password; the provision script
# owns setting it (IMPLEMENTATION_CONVENTIONS.md, Database section).
log "Setting app_user / app_service passwords"
( cd "$FIRM_DIR" && docker compose -p "$FIRM_SLUG" exec -T db \
    psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
    -c "ALTER ROLE app_user    WITH LOGIN PASSWORD '${APP_USER_PASSWORD}';" \
    -c "ALTER ROLE app_service WITH LOGIN PASSWORD '${APP_USER_PASSWORD}';" )

# --------------------------------------------------------------------------
# 7. Build and start the application services
# --------------------------------------------------------------------------
# Build the shared backend image ONCE (backend + both workers reuse it) and the
# frontend image, then start the whole stack. Building first avoids the compose
# race where the three services sharing one image build it in parallel and
# collide ("image ... already exists").

log "Building application images (backend, frontend)"
( cd "$FIRM_DIR" && docker compose -p "$FIRM_SLUG" build backend frontend )

log "Starting application services"
( cd "$FIRM_DIR" && docker compose -p "$FIRM_SLUG" up -d )

# --------------------------------------------------------------------------
# 8. Summary
# --------------------------------------------------------------------------

cat <<SUMMARY

============================================================================
 Firm provisioned: ${FIRM_SLUG}
============================================================================

 URLs (via Traefik wildcard TLS):
   Dashboard : https://${FIRM_SLUG}.${BASE_DOMAIN}
   API       : https://api.${FIRM_SLUG}.${BASE_DOMAIN}

 Secrets:
   All fresh secrets (POSTGRES_PASSWORD, JWT_SECRET, ANON_KEY,
   SERVICE_ROLE_KEY, APP_USER_PASSWORD, DASHBOARD_PASSWORD) live ONLY in:
     ${ENV_FILE}            (chmod 600)
   They are never logged and never reused across firms. Back this file up
   securely — losing JWT_SECRET invalidates all issued tokens.

 Remaining manual steps:
   1. WAHA WhatsApp: create this firm's WAHA Plus session (Sumopod), then
      enter the WAHA URL + API key in the dashboard under Settings
      (firm_settings) — secrets belong in the DB settings table, not .env.
   2. LLM: enter the client-provided LLM API key (and embedding config) in
      Settings (firm_settings) via the dashboard.
   3. Supabase Studio is NOT publicly exposed [C-XI] — it binds to
      127.0.0.1:54323 on this host. To use it, open an SSH tunnel:
        ssh -L 54323:127.0.0.1:54323 <admin>@<this-host>
      then browse http://localhost:54323.
   4. Run the security baseline audit:
        ${REPO_ROOT}/infra/security/check_baseline.sh ${FIRM_SLUG}
   5. Before onboarding real data, prove a backup restores:
        ${REPO_ROOT}/infra/backup/backup_restore_test.sh ${FIRM_SLUG}
        ${REPO_ROOT}/infra/backup/backup_restore_test.sh ${FIRM_SLUG} --restore-test

============================================================================
SUMMARY
