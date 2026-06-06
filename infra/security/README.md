# Self-Hosting Security Baseline (`infra/security`) — [C-XI]

Constitution Principle XI: *"Production deployments MUST use fresh production
secrets (never defaults), SSL everywhere, protected admin/Studio interfaces, a
firewall, and automated backups that are tested for restore (not merely
taken)."* This directory enforces and audits that baseline.

## The [C-XI] checklist

Every item must hold **before any real firm is onboarded**, and stays true for
the life of the deployment:

- [ ] **Fresh secrets — never defaults.** Every firm's `POSTGRES_PASSWORD`,
      `JWT_SECRET`, `ANON_KEY`, `SERVICE_ROLE_KEY`, `APP_USER_PASSWORD` and
      `DASHBOARD_PASSWORD` are generated per firm by
      `infra/provision/provision_firm.sh` (openssl rand + HS256-derived JWTs).
      No `CHANGE_ME`, no Supabase demo secrets, no value reused across firms.
      Secrets live only in `/opt/firms/<slug>/.env` (chmod 600) and the
      `firm_settings` table (WAHA/LLM keys, masked by the API, logged
      action-only [C-III]).
- [ ] **SSL everywhere.** Traefik terminates TLS for every subdomain with a
      wildcard Let's Encrypt certificate; port 80 only redirects/answers ACME.
      No plaintext app traffic crosses the host boundary.
- [ ] **Studio protected.** Supabase Studio is never published beyond
      `127.0.0.1` — access is via SSH tunnel + basic-auth only.
- [ ] **Firewall.** ufw active: default deny incoming; only 22/80/443 open
      (`harden_host.sh`). Nothing else is published by any container.
- [ ] **Tested backups.** Per-firm automated backups exist **and a restore
      test has passed** (`infra/backup/backup_restore_test.sh <slug>
      --restore-test`). An untested backup is not a backup.

## Scripts

### `harden_host.sh` (run once per host, as root — idempotent)

```bash
sudo ./harden_host.sh
```

- ufw: default deny incoming / allow outgoing; allow `22,80,443/tcp`; enable.
- fail2ban: enables it if installed, otherwise prints the install hint.
- Prints the Docker `live-restore` recommendation for `/etc/docker/daemon.json`.

Note on Docker vs ufw: Docker-published ports bypass ufw via iptables. The
stack therefore publishes **nothing** except Traefik's 80/443; the database,
Kong and Studio stay on internal networks or bind `127.0.0.1`.

### `check_baseline.sh` (run per firm, after provisioning and on a schedule)

```bash
./check_baseline.sh <firm-slug>     # exit 0 = pass, 1 = fail with ✗ list
```

Audits: `.env` present + chmod 600; no placeholder/default/empty secrets;
Studio bound to `127.0.0.1` only; Traefik `acme.json` chmod 600; ufw active.

Wire it into monitoring/cron alongside the backup jobs — a regression in any
item is an incident, not a TODO.
