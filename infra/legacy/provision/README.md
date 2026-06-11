# Per-Firm Provisioning (`infra/provision`) — [C-XI]

Stands up one **fully isolated** firm instance (constitution Principle I): its own
Docker stack, its own Postgres + pgvector, its own GoTrue auth, its own Storage —
never shared with any other firm.

```bash
./provision_firm.sh <firm-slug> <base-domain>
# e.g.
./provision_firm.sh alfarouk example-legal.com
```

Result:

| What | Where |
|---|---|
| Firm stack files | `/opt/firms/<slug>/` (compose, volumes, kong.yml) |
| Fresh secrets | `/opt/firms/<slug>/.env` (chmod 600 — **never defaults** [C-XI]) |
| Dashboard | `https://<slug>.<base-domain>` |
| Backend API | `https://api.<slug>.<base-domain>` |
| Compose project | `docker compose -p <slug> …` |

## Prerequisites (do these once per host, before the first firm)

1. **Docker + docker compose v2** installed; `openssl` and `envsubst`
   (`apt install gettext-base`) available.
2. **Traefik is up** as the single host-wide reverse proxy:
   `infra/traefik/docker-compose.traefik.yml`. It owns ports 80/443 and the
   Let's Encrypt wildcard certificate.
3. **The external `proxy` docker network exists** (Traefik and every firm stack
   attach to it):
   ```bash
   docker network create proxy   # no-op if it already exists
   ```
4. **Wildcard DNS**: `*.<base-domain>` (and `*.api.<base-domain>` if you use a
   separate API zone — the default layout only needs `*.<base-domain>` plus
   `api.<slug>.<base-domain>` covered by the wildcard) points at this host.
   Traefik requests a wildcard Let's Encrypt cert via the DNS-01 challenge.
5. **Host hardened**: run `infra/security/harden_host.sh` (ufw deny-in,
   allow 22/80/443) before exposing anything.
6. The repository is checked out on the host — the script copies
   `infra/docker-compose.yml`, the `infra/volumes-template/` tree, and applies
   `supabase/migrations/*.sql`.

## What the script generates (fresh, per firm — never reused)

- `POSTGRES_PASSWORD` — `openssl rand -hex 24`
- `JWT_SECRET` — `openssl rand -hex 32` (GoTrue / Kong / backend HS256)
- `ANON_KEY`, `SERVICE_ROLE_KEY` — HS256 JWTs (`role=anon` / `role=service_role`,
  `iss=supabase`, 10-year expiry) signed with the fresh `JWT_SECRET`
- `APP_USER_PASSWORD` — backend `app_user` DB role password (set post-migration)
- `DASHBOARD_PASSWORD` — Supabase Studio basic-auth

All land **only** in `/opt/firms/<slug>/.env` (mode 600). Re-running the script
for an existing firm refuses to overwrite the `.env` — secrets are generated
exactly once.

## After provisioning — the WAHA session step

Each firm gets its **own WAHA Plus session** (Sumopod); the session is the
firm's WhatsApp tenant identifier:

1. Create a session for the firm in WAHA Plus (Sumopod console), scan the QR
   with the firm's WhatsApp number.
2. Log into the firm dashboard as the partner/manager and open **Settings**.
3. Enter the WAHA base URL + API key and the session name into `firm_settings`.
   These secrets live in the database settings table — **not** in `.env` —
   and the audit log records only that a key was set, never its value [C-III].
4. While you are there, enter the client-provided **LLM API key** and the
   embedding configuration.

## Supabase Studio access (never public) [C-XI]

Studio binds to `127.0.0.1:54323` only (see `infra/docker-compose.yml`). To use it:

```bash
ssh -L 54323:127.0.0.1:54323 <admin>@<host>
# then open http://localhost:54323
```

## Before onboarding a real firm

- `infra/security/check_baseline.sh <slug>` must pass.
- `infra/backup/backup_restore_test.sh <slug> --restore-test` must PASS —
  **no real firm is onboarded until a restore test has succeeded** [C-XI].
