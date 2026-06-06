# Implementation Conventions (binding for all contributors/agents)

These conventions pin down every cross-file contract so independently written modules compose.
Authoritative upstream docs: `.specify/memory/constitution.md`, `specs/001-lawyer-office-management/`
(plan, data-model, contracts, research). On conflict, the constitution wins.

## Backend (Python 3.12, FastAPI)

- Package root: `backend/app`. App entry: `app.main:app` (uvicorn). Workers live in
  `backend/workers/` and run with `backend/` as CWD: `python -m workers.pipeline_worker`,
  `python -m workers.scheduler_worker`.
- Dependencies (pyproject, managed with `uv`): `fastapi`, `uvicorn[standard]`, `pydantic>=2`,
  `pydantic-settings`, `asyncpg`, `pyjwt`, `httpx`, `python-multipart`, `apscheduler`.
  Dev: `ruff`, `pytest`, `pytest-asyncio`.
- **DB access**: raw parameterized SQL via `asyncpg` pool — no ORM. Helpers in
  `app/core/db.py`:
  - `get_pool() -> asyncpg.Pool` (lazy singleton)
  - `db_connection(user: CurrentUser | None)` async contextmanager that acquires a connection
    and, when `user` is given, runs
    `SELECT set_config('app.user_id', $1, false), set_config('app.user_role', $2, false), set_config('app.context', $3, false)`
    so the **audit triggers** capture who/role/context; resets via `RESET ALL` on release.
  - FastAPI dependency `Db = Annotated[asyncpg.Connection, Depends(get_db)]` — `get_db`
    yields a per-request connection with the GUCs set from the authenticated user.
- **Auth** (`app/core/security.py`): verify GoTrue JWT (HS256, `settings.gotrue_jwt_secret`,
  audience `authenticated`) from `Authorization: Bearer`. Load the `users` row by
  `auth_user_id = token.sub`; reject missing or `status != 'active'` with 401. Expose:
  - `class CurrentUser(BaseModel): id: UUID; auth_user_id: UUID; full_name: str; email: str; phone: str | None; role: Role; status: str`
  - dependency `CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]`
- **RBAC** (`app/core/rbac.py`):
  - `Role = Literal["partner_manager", "lawyer", "paralegal", "secretary"]`
  - `require_roles(*roles: str)` → FastAPI dependency factory raising 403.
  - `async def assert_case_access(conn, user, case_id, *, manager_ok=True)` → 404 if the case
    doesn't exist, 403 if the user is neither assigned (via `case_assignments`) nor a manager.
- **Feature flags** (`app/core/flags.py`): `async def get_flag(conn, name: str) -> bool` reads
  the singleton `firm_settings` row (e.g. `feature_appeal_deadlines`).
- **Errors**: every error response uses `{"error": {"code": str, "message": str}}`.
  `app/main.py` installs handlers mapping `HTTPException`/validation errors to that envelope.
  Raise `ApiError(status_code, code, message)` (defined in `app/core/errors.py`) in services.
  Codes are lower_snake (e.g. `not_found`, `forbidden`, `invalid_state`, `review_gate_blocked`).
- **Models** (`app/models/`): pydantic v2 models per entity, one module per entity group, all
  re-exported from `app/models/__init__.py`. Field names exactly match DB columns
  (see data-model.md). Enums as `Literal[...]` type aliases.
- **Routers**: one module per area in `app/api/` exposing `router = APIRouter()`;
  `app/main.py` includes them with the paths from `contracts/rest-api.md` (paths are the
  contract — no `/api/v1` prefix). Every mutation happens through a connection carrying the
  audit GUCs (the DB triggers do the audit writing — never hand-write audit rows except via
  `app/audit/audit.py` helpers for verification).
- **Settings** (`app/core/config.py`, pydantic-settings, env-driven; env var = upper of field):
  `database_url`, `gotrue_jwt_secret`, `supabase_url`, `supabase_service_key`,
  `storage_bucket="documents"`, `docai_project_id`, `docai_location`, `docai_processor_id`,
  `google_application_credentials`, `ocr_confidence_threshold=0.80`,
  `chunk_tokens=800`, `chunk_overlap_tokens=120`, `embedding_dimension=1536`,
  `shared_corpus_database_url=""` (empty → shared corpus disabled), `worker_poll_seconds=5`.
  Secrets (LLM key, WAHA key/url, embedding config) live in **`firm_settings` table**, not env.
- **No prints**; use `logging` (`logger = logging.getLogger(__name__)`).

## Database (Postgres 15 + pgvector, migrations in `supabase/migrations/`)

- Files run in lexical order: `0001_extensions.sql` … `0008_review_gate.sql`. Idempotent where
  possible (`create … if not exists`).
- All PKs `uuid primary key default gen_random_uuid()`. Timestamps `timestamptz default now()`.
- Embeddings: `vector(1536)`, HNSW index `vector_cosine_ops`.
- App connects as role `app_user` (created in migrations; the provision script sets its
  password). RLS policies target `app_user` reading GUCs `app.user_id` / `app.user_role`.
  GoTrue/Storage manage their own schemas — our migrations only touch `public`.
- `users.auth_user_id uuid unique` links to GoTrue's `auth.users.id` (no hard FK — GoTrue owns
  that schema).
- Audit triggers: a single generic trigger function `audit_trigger()` reads
  `current_setting('app.user_id', true)`, `app.user_role`, `app.context`; computes field-level
  old→new JSON diff; **redacts** secret columns (`waha_key`, `llm_api_key`) as
  `"[REDACTED]" → "[REDACTED]"`; inserts into `audit_log`. Attached to every audited table
  (all except `audit_log` itself).
- Append-only: `REVOKE UPDATE, DELETE ON audit_log FROM app_user; GRANT INSERT, SELECT`.

## Frontend (Next.js 14 App Router, TypeScript, Tailwind, RTL Arabic)

- `frontend/` with `app/`, `components/`, `lib/`, `tests/`. Strict TS. Tailwind for styling.
- Root layout: `<html lang="ar" dir="rtl">`; all UI copy in **Arabic** (keep technical values
  Latin). Font: system Arabic stack (no external font fetch).
- `lib/supabase.ts`: browser client from `NEXT_PUBLIC_SUPABASE_URL` /
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` (`@supabase/supabase-js`), plus `getSession()` helper.
- `lib/api.ts`: `api<T>(path, init?)` fetch wrapper → `NEXT_PUBLIC_API_URL` + path, attaches
  `Authorization: Bearer <access_token>` from the supabase session, parses the error envelope
  and throws `ApiError { code, message, status }`.
- `lib/rbac.ts`: `Role` type, `useUser()` (fetches `/me` once, context-cached via
  `<UserProvider>` in the root layout), `<RequireRole roles={[...]}>` client guard component
  that redirects unauthorized users to `/dashboard` (or `/login` when unauthenticated).
- Shared components (`components/`):
  - `<Disclaimer/>` — persistent footer banner: "أداة مساعدة — ليست استشارة قانونية. تبقى
    المسؤولية المهنية على المحامي." Rendered in the root layout on every screen.
  - `<AiMarkedOutput output={AiOutput}>` — renders the banner
    "محتوى مولّد بالذكاء الاصطناعي — يتطلب المراجعة" while `review_state !== 'approved'`,
    the content, per-claim source links (`source_links` → `/documents/{id}?chunk=`),
    and a **heightened red warning** when `low_confidence_flag`.
  - `<ReviewGate output={AiOutput}>` — wraps export/print/send affordances; children disabled
    (with explanatory tooltip) unless `review_state === 'approved'`.
- Screens live at `app/<area>/page.tsx` ('use client' pages calling `lib/api.ts`):
  login, dashboard, cases, cases/[id], documents, ai-review, deadlines, tasks, assistant,
  reports, settings, users, audit. Each screen declares roles per `contracts/ui-screens.md`
  via `<RequireRole>`.
- Types mirroring API payloads live in `lib/types.ts` (single source for the frontend).

## Infra

- `infra/docker-compose.yml` is the **single per-firm stack**: Supabase self-host services
  (db with pgvector, gotrue/auth, storage, kong gateway, studio), `backend` (image built from
  `backend/Dockerfile`), `worker-pipeline`, `worker-scheduler` (same image, different
  entrypoint), `frontend`. All firm-specific values come from `.env` (written by the provision
  script from `infra/provision/env.template`). Compose project name = firm slug.
- Traefik runs **once per host** (separate `infra/traefik/docker-compose.traefik.yml`),
  attaches to external docker network `proxy`, routes `<firm>.<DOMAIN>` (frontend) and
  `api.<firm>.<DOMAIN>` (backend) via labels on each firm stack.
- Scripts are bash (`#!/usr/bin/env bash`, `set -euo pipefail`) — they run on the Linux
  host/VPS, not Windows.

## Cross-cutting rules (constitution)

- AI outputs: born `draft_unreviewed`; export endpoints 403 anything else **[C-II]**.
- Audit: never bypass; mutations go through audited connections **[C-III]**.
- Reminders/reports: deterministic code only; LLM phrases prose at most **[C-IV]**.
- Grounding: `source_links` (list of `{chunk_id, document_id, page_ref}`) on every AI claim **[C-V]**.
- Appeal deadlines: flag-gated, `confirmed=false`, inert until confirmed **[C-X]**.
- Secrets never logged as values; settings API returns them masked **[C-III][C-XI]**.
