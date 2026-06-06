# Traefik — host-level reverse proxy (one per host, NOT per firm)

Traefik terminates TLS for **every** firm stack on this host and routes
subdomains to the right firm container over the shared `proxy` Docker network.
Firm stacks register themselves purely via container labels — adding a firm
requires **no Traefik change or restart**.

```text
Internet ──443──> Traefik ──proxy network──> firm-a frontend / backend / kong
                                          └─> firm-b frontend / backend / kong
```

Files in this directory:

| File | Purpose |
|---|---|
| `docker-compose.traefik.yml` | The Traefik service (run once per host) |
| `traefik.yml` | Static config: entrypoints, docker+file providers, ACME DNS-01 resolver |
| `dynamic/dashboard.yml` | Dashboard router (localhost entrypoint + basic auth) |
| `.env.traefik.template` | Template for the Cloudflare DNS API token |

## 1. One-time host setup

### 1.1 Create the shared proxy network

```bash
docker network create proxy
```

Every firm stack's `docker-compose.yml` declares `proxy` as
`external: true` and attaches only its public-facing services
(`frontend`, `backend`, `kong`) to it. Everything else (db, auth, storage,
studio, workers) stays on the firm's private `internal` network — Traefik
cannot reach those, by construction.

### 1.2 Wildcard DNS

Point a wildcard record at this host's public IP in your DNS provider
(Cloudflare):

```text
A    example.com      <host IP>
A    *.example.com    <host IP>
```

Each firm lives at `<slug>.example.com` with services on
`api.<slug>.example.com` and `supabase.<slug>.example.com`. Note that a
single `*.example.com` record does **not** resolve second-level names like
`api.<slug>.example.com` — add one wildcard per firm:

```text
A    *.<slug>.example.com    <host IP>
```

(The provision script can create this via the Cloudflare API using the same
token as below.)

For the home **demo** server, skip public DNS/ports entirely and expose via
Cloudflare Tunnel instead — dummy data only, never real client documents.

### 1.3 DNS-01 token (wildcard Let's Encrypt)

Wildcard certificates require the **DNS-01** challenge. Create a Cloudflare
API token with `Zone -> DNS -> Edit` on the relevant zone(s), then:

```bash
cd infra/traefik
cp .env.traefik.template .env
# edit .env -> set CF_DNS_API_TOKEN (never commit .env)
```

Also edit `traefik.yml` and set a real `email:` under
`certificatesResolvers.letsencrypt.acme` (static config does not expand env
vars).

### 1.4 ACME storage + dashboard credential

```bash
touch acme.json
chmod 600 acme.json            # Traefik refuses acme.json with looser perms

htpasswd -nB admin             # paste the output into dynamic/dashboard.yml
```

Never leave the placeholder hash in `dynamic/dashboard.yml` — fresh
credentials on every host. [C-XI]

### 1.5 Start

```bash
docker compose -f docker-compose.traefik.yml up -d
docker logs -f traefik         # watch the first certificate issuance
```

## 2. How firm stacks register routes

Nothing is configured here per firm. Each firm's compose file carries labels
like:

```yaml
labels:
  - "traefik.enable=true"                                   # opt-in (exposedByDefault=false)
  - "traefik.docker.network=proxy"
  - "traefik.http.routers.${FIRM_SLUG}-app.rule=Host(`${FIRM_DOMAIN}`)"
  - "traefik.http.routers.${FIRM_SLUG}-app.entrypoints=websecure"
  - "traefik.http.routers.${FIRM_SLUG}-app.tls.certresolver=letsencrypt"
  - "traefik.http.routers.${FIRM_SLUG}-app.tls.domains[0].main=${FIRM_DOMAIN}"
  - "traefik.http.routers.${FIRM_SLUG}-app.tls.domains[0].sans=*.${FIRM_DOMAIN}"
  - "traefik.http.services.${FIRM_SLUG}-app.loadbalancer.server.port=3000"
```

Traefik watches the Docker socket; the moment a firm stack starts, the routes
go live and a wildcard certificate (`<firm-domain>` + `*.<firm-domain>`) is
requested via DNS-01. Router/service names are prefixed with the firm slug so
stacks never collide.

Per-firm routes:

| Host | Service | Container port |
|---|---|---|
| `${FIRM_DOMAIN}` | frontend (Next.js dashboard) | 3000 |
| `api.${FIRM_DOMAIN}` | backend (FastAPI) | 8000 |
| `supabase.${FIRM_DOMAIN}` | kong (GoTrue/PostgREST/Storage gateway) | 8000 |

## 3. Security posture [C-XI]

- Port 80 only redirects to 443 — no plaintext serving.
- `exposedByDefault: false` — containers must opt in with `traefik.enable=true`.
- The dashboard listens on a dedicated entrypoint bound to `127.0.0.1:8081`
  and is basic-auth protected. Reach it via SSH tunnel:
  `ssh -L 8081:127.0.0.1:8081 <host>` then open `http://localhost:8081`.
- Supabase Studio is **not** routed by Traefik at all — firm stacks bind it to
  `127.0.0.1:54323` on the host (SSH tunnel only).
- Docker socket is mounted read-only.
- Host firewall should allow inbound 80/443 (and SSH) only — see
  `infra/security/`.
