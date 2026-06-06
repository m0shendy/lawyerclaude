#!/usr/bin/env bash
#
# harden_host.sh — One-time host hardening for a firm-hosting Docker box.  [C-XI]
#
# Usage:
#   sudo ./harden_host.sh
#
# What it does (idempotent — safe to re-run):
#   1. ufw: default deny incoming / allow outgoing; allow 22 (SSH), 80, 443;
#      enable non-interactively.
#   2. fail2ban: install hint + enable if present (SSH brute-force protection).
#   3. Docker daemon: prints the `live-restore` recommendation so container
#      workloads survive a docker daemon restart.
#
# Run BEFORE provisioning the first firm. Constitution Principle XI requires
# a host firewall as part of the self-hosting security baseline.

set -euo pipefail

log()  { printf '\033[1;34m[harden]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[harden] WARN:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[harden] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "must run as root (sudo $0)"

# --------------------------------------------------------------------------
# 1. Firewall (ufw): deny everything inbound except SSH + HTTP(S)
# --------------------------------------------------------------------------

command -v ufw >/dev/null || die "ufw is not installed (apt install ufw)"

log "Configuring ufw (idempotent — re-applying rules is a no-op)"

# Defaults: nothing comes in unless explicitly allowed; everything may go out.
ufw default deny incoming
ufw default allow outgoing

# 22  — SSH (admin access + the Studio SSH tunnel; consider moving to a
#       non-standard port and/or restricting to your admin IPs).
# 80  — HTTP (Traefik: ACME HTTP-01 + redirect-to-HTTPS only).
# 443 — HTTPS (Traefik: all firm dashboards + APIs, wildcard TLS).
ufw allow 22/tcp  comment 'SSH (admin + Studio tunnel)'
ufw allow 80/tcp  comment 'HTTP -> Traefik (redirect/ACME)'
ufw allow 443/tcp comment 'HTTPS -> Traefik'

# Enable without the interactive y/N prompt. `ufw --force enable` is
# idempotent: if already active it just reloads.
ufw --force enable
log "ufw status:"
ufw status verbose | sed 's/^/    /'

# NOTE on Docker + ufw: Docker's published ports manipulate iptables directly
# and can bypass ufw. This stack avoids the problem by publishing NOTHING
# except Traefik's 80/443; everything else (db, kong, studio) stays on
# internal docker networks or binds to 127.0.0.1. check_baseline.sh verifies
# the Studio binding per firm.

# --------------------------------------------------------------------------
# 2. fail2ban — SSH brute-force protection
# --------------------------------------------------------------------------

if command -v fail2ban-server >/dev/null 2>&1; then
  log "fail2ban present — ensuring it is enabled and running"
  systemctl enable --now fail2ban
  log "fail2ban active jails: $(fail2ban-client status 2>/dev/null | grep 'Jail list' || echo 'n/a')"
else
  warn "fail2ban is NOT installed. Strongly recommended:"
  warn "    apt install fail2ban && systemctl enable --now fail2ban"
  warn "The default sshd jail is sufficient for this baseline."
fi

# --------------------------------------------------------------------------
# 3. Docker daemon live-restore note
# --------------------------------------------------------------------------

DAEMON_JSON=/etc/docker/daemon.json
if [[ -f "$DAEMON_JSON" ]] && grep -q '"live-restore"[[:space:]]*:[[:space:]]*true' "$DAEMON_JSON"; then
  log "Docker live-restore is already enabled in ${DAEMON_JSON}"
else
  warn "Recommended: enable Docker live-restore so firm stacks keep running"
  warn "across docker-daemon restarts/upgrades. Add to ${DAEMON_JSON}:"
  warn '    { "live-restore": true }'
  warn "then: systemctl reload docker"
  warn "(Not changed automatically — daemon.json may carry other settings.)"
fi

log "Host hardening complete. Next: provision firms, then run check_baseline.sh per firm."
