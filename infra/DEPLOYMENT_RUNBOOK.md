# Deployment Runbook — Home → VPS Lift-and-Shift (T100) [C-XI]

Per-firm, physically-isolated deployment. Each firm = one self-hosted Supabase
stack + backend + workers + frontend behind Traefik (wildcard TLS) or a
Cloudflare tunnel. **Every firm gets FRESH production secrets** — never reuse a
dev/home key in prod. [C-XI]

## 0. Prerequisites

- VPS (Linux, Docker + Docker Compose v2), root or sudo.
- A domain with wildcard DNS (`*.firmdomain`) → VPS, or a Cloudflare tunnel.
- This repo on the VPS (e.g. `/home/<user>/lawyerclaude`).
- `infra/provision/provision_firm.sh` and `infra/provision/env.template`.

## 1. Generate FRESH production secrets (never copy from home)

Per firm, generate new values for: `POSTGRES_PASSWORD`, `JWT_SECRET`,
`ANON_KEY`, `SERVICE_ROLE_KEY`, `APP_USER_PASSWORD`, `DASHBOARD_PASSWORD`.
Firm-owned secrets (LLM API key, WAHA url/key) are entered later via the
**Settings** screen, never baked into images. [C-III][C-XI]

## 2. Provision the firm stack

```bash
cd infra/provision
./provision_firm.sh <firm-slug> <base-domain>
```
This renders `docker-compose.yml`, starts core services, runs migrations
(`supabase/migrations/0001..0010`), then builds + starts backend, workers, and
frontend. Firm data lives under `/opt/firms/<slug>`.

## 3. DNS + wildcard TLS

- **Traefik path:** point `*.<base-domain>` at the VPS; Traefik (see
  `infra/traefik/`) obtains Let's Encrypt certs automatically (`acme.json`).
- **Cloudflare tunnel path:** run `cloudflared` with an ingress rule mapping
  `<firm>.<domain>` → `frontend:3000` (and the API host if exposed separately).

## 4. Configure firm secrets (Settings screen, manager)

Log in as the firm manager → **الإعدادات**: enter WAHA URL/key, LLM API key,
embedding model/dimension, reminder lead points. Secrets are masked and audited
as action-only. [C-III]

## 5. Verify

```bash
docker compose -p <slug> ps                    # all healthy
curl -s -o /dev/null -w '%{http_code}' https://<firm>.<domain>/dashboard   # 200
docker exec <slug>-backend-1 wget -qO- http://localhost:8000/health        # ok
docker logs <slug>-worker-scheduler-1 --tail 5 # reminders + reports jobs registered
```

## 6. Redeploying code changes (IMPORTANT — avoids stale builds)

The frontend bakes `NEXT_PUBLIC_*` at build time and both images `COPY` source,
so **always rebuild, don't just restart**:
```bash
# sync latest source to the VPS checkout first (it is NOT a git deploy), then:
cd /opt/firms/<slug>
docker compose -p <slug> build --no-cache backend frontend
docker compose -p <slug> up -d
```
A plain `up -d` without `build` will keep serving the old code. See
`MEMORY: deploy-source-drift`.

## 7. Before real onboarding

- Run the **backup restore test** (`infra/backup/RESTORE_TEST.md`).
- Confirm appeal-deadline feature stays **off** (`docs/APPEAL_DEADLINES_SIGNOFF.md`).
- Confirm the assistive-tool ToS copy is presented (`docs/TERMS_AND_POSTURE.md`).
