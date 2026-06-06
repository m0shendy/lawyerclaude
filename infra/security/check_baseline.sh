#!/usr/bin/env bash
#
# check_baseline.sh — Audit one firm instance against the [C-XI] security
# baseline. Read-only: changes nothing, only reports.
#
# Usage:
#   ./check_baseline.sh <firm-slug>
#
# Checks:
#   1. /opt/firms/<slug>/.env exists and is chmod 600.
#   2. No default/placeholder/empty secrets in .env (CHANGE_ME, empty values
#      for the critical keys, and known Supabase demo secrets).
#   3. Supabase Studio is not publicly exposed — its container port may only
#      be bound to 127.0.0.1 (or not published at all).
#   4. Traefik's acme.json (Let's Encrypt account/cert store) is chmod 600.
#   5. ufw is active.
#
# Exit code: 0 when every check passes; 1 otherwise, with a ✗ list.

set -euo pipefail

FIRMS_ROOT="${FIRMS_ROOT:-/opt/firms}"

usage() { echo "Usage: $(basename "$0") <firm-slug>" >&2; exit 64; }
[[ $# -eq 1 ]] || usage
FIRM_SLUG="$1"
[[ "$FIRM_SLUG" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || usage

FIRM_DIR="${FIRMS_ROOT}/${FIRM_SLUG}"
ENV_FILE="${FIRM_DIR}/.env"

PASSES=()
FAILS=()
pass() { PASSES+=("$1"); }
fail() { FAILS+=("$1"); }

# --------------------------------------------------------------------------
# 1. .env exists and is private (600)
# --------------------------------------------------------------------------

if [[ -f "$ENV_FILE" ]]; then
  pass ".env exists at ${ENV_FILE}"
  perms="$(stat -c '%a' "$ENV_FILE")"
  if [[ "$perms" == "600" ]]; then
    pass ".env permissions are 600"
  else
    fail ".env permissions are ${perms}, expected 600 (fix: chmod 600 ${ENV_FILE})"
  fi
else
  fail ".env not found at ${ENV_FILE} — firm not provisioned?"
fi

# --------------------------------------------------------------------------
# 2. No default / placeholder / empty secrets  [C-XI: fresh secrets, never defaults]
# --------------------------------------------------------------------------

if [[ -f "$ENV_FILE" ]]; then
  # 2a. Placeholder markers anywhere in the file.
  if grep -qiE 'CHANGE_ME|CHANGEME|your-secret|example-secret' "$ENV_FILE"; then
    fail ".env contains placeholder secrets (CHANGE_ME/…): $(grep -ciE 'CHANGE_ME|CHANGEME|your-secret|example-secret' "$ENV_FILE") line(s)"
  else
    pass "no placeholder markers (CHANGE_ME etc.) in .env"
  fi

  # 2b. Known Supabase self-host DEMO secrets (shipped in their docs/compose) —
  #     these would allow anyone on the internet to forge tokens.
  if grep -qE 'super-secret-jwt-token-with-at-least-32-characters|this_password_is_insecure' "$ENV_FILE"; then
    fail ".env contains a known Supabase DEMO secret — regenerate fresh secrets"
  else
    pass "no known Supabase demo secrets in .env"
  fi

  # 2c. Critical keys must be present and non-empty.
  for key in POSTGRES_PASSWORD JWT_SECRET ANON_KEY SERVICE_ROLE_KEY; do
    # value = text after the first '=' on the key's line, trimmed.
    value="$(grep -E "^${key}=" "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d '[:space:]')"
    if [[ -z "$value" ]]; then
      fail "${key} is missing or empty in .env"
    else
      pass "${key} is set and non-empty"
    fi
  done
fi

# --------------------------------------------------------------------------
# 3. Studio not publicly exposed (127.0.0.1-bound or unpublished)
# --------------------------------------------------------------------------

# Match this firm's studio container by compose project label naming
# convention: <slug>-studio-1 (compose v2) or <slug>_studio_1 (legacy).
studio_ports="$(docker ps --filter "name=${FIRM_SLUG}[-_]studio" --format '{{.Ports}}' 2>/dev/null || true)"

if [[ -z "$studio_ports" ]]; then
  # Not running or not published at all — not publicly exposed either way,
  # but distinguish for the operator.
  if docker ps -a --filter "name=${FIRM_SLUG}[-_]studio" --format '{{.Names}}' 2>/dev/null | grep -q .; then
    pass "studio container exists but is not currently exposing ports"
  else
    fail "studio container for '${FIRM_SLUG}' not found (is the stack up? docker compose -p ${FIRM_SLUG} ps)"
  fi
else
  # Any published binding that is NOT 127.0.0.1 (e.g. 0.0.0.0:3000-> or [::]:3000->)
  # means Studio is reachable from outside — a baseline violation.
  if echo "$studio_ports" | grep -E '(^|, )(0\.0\.0\.0|\[::\]|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+):' \
       | grep -vq '127\.0\.0\.1:'; then
    fail "studio port is publicly bound: '${studio_ports}' — must bind 127.0.0.1 only (SSH tunnel access)"
  else
    pass "studio bound to 127.0.0.1 only: '${studio_ports}'"
  fi
fi

# --------------------------------------------------------------------------
# 4. Traefik acme.json permissions (600)
# --------------------------------------------------------------------------

ACME_CANDIDATES=(
  "${ACME_JSON:-}"                      # explicit override
  /opt/traefik/acme.json
  /opt/traefik/letsencrypt/acme.json
  /etc/traefik/acme.json
)
acme_found=""
for candidate in "${ACME_CANDIDATES[@]}"; do
  [[ -n "$candidate" && -f "$candidate" ]] && { acme_found="$candidate"; break; }
done

if [[ -n "$acme_found" ]]; then
  perms="$(stat -c '%a' "$acme_found")"
  if [[ "$perms" == "600" ]]; then
    pass "acme.json (${acme_found}) permissions are 600"
  else
    fail "acme.json (${acme_found}) permissions are ${perms}, expected 600 (Traefik refuses >600 anyway)"
  fi
else
  fail "acme.json not found (looked in /opt/traefik, /etc/traefik; set ACME_JSON=/path to override)"
fi

# --------------------------------------------------------------------------
# 5. ufw active
# --------------------------------------------------------------------------

if command -v ufw >/dev/null 2>&1; then
  # `ufw status` needs root to read the state; degrade gracefully.
  ufw_status="$(ufw status 2>/dev/null || sudo -n ufw status 2>/dev/null || echo 'unknown')"
  if echo "$ufw_status" | grep -q '^Status: active'; then
    pass "ufw is active"
  elif [[ "$ufw_status" == "unknown" ]]; then
    fail "could not read ufw status (run as root: sudo $0 ${FIRM_SLUG})"
  else
    fail "ufw is NOT active (run infra/security/harden_host.sh)"
  fi
else
  fail "ufw is not installed (run infra/security/harden_host.sh)"
fi

# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

echo
echo "Security baseline audit for firm '${FIRM_SLUG}'  [C-XI]"
echo "------------------------------------------------------------"
for p in "${PASSES[@]:-}"; do [[ -n "$p" ]] && echo "  ✓ $p"; done
for f in "${FAILS[@]:-}";  do [[ -n "$f" ]] && echo "  ✗ $f"; done
echo "------------------------------------------------------------"

if (( ${#FAILS[@]} > 0 )); then
  echo "RESULT: FAIL — ${#FAILS[@]} check(s) failed. Fix before onboarding real data."
  exit 1
fi
echo "RESULT: PASS — baseline satisfied (remember: backups must also pass a restore test)."
