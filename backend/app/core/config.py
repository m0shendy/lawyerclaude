"""Application settings (T018).

Environment-driven via pydantic-settings; env var name = upper-case of field.
Secrets that belong to the FIRM (LLM key, WAHA url/key, embedding config) live
in the `firm_settings` table — NOT here. Here lives only what the instance
needs to boot: DB, auth secret, storage, Document AI, and tunable knobs.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database (per-firm Postgres; fresh credentials per provision [C-XI])
    # API requests connect as app_user (RLS-enforced). Background workers and
    # other system contexts (user=None) connect via service_database_url, an
    # app_service role with BYPASSRLS — they legitimately operate across all
    # rows. Falls back to database_url if unset (then RLS would hide rows from
    # workers, so it MUST be set for the pipeline to work).
    database_url: str = "postgresql://app_user:postgres@localhost:5432/postgres"
    service_database_url: str = ""

    # Supabase (per-firm stack)
    gotrue_jwt_secret: str = ""  # MUST be set per instance — never a default [C-XI]
    supabase_url: str = "http://kong:8000"
    supabase_service_key: str = ""
    storage_bucket: str = "documents"

    # Google Document AI (live OCR intake)
    docai_project_id: str = ""
    docai_location: str = "eu"
    docai_processor_id: str = ""
    google_application_credentials: str = ""

    # Pipeline knobs (defaults from research.md; tune at the T052 checkpoint)
    ocr_confidence_threshold: float = 0.80  # R4 [C-VII]
    chunk_tokens: int = 800  # R3
    chunk_overlap_tokens: int = 120  # R3
    embedding_dimension: int = 1536  # R1

    # Shared Egyptian-law corpus (central read-only service; empty = disabled) [C-I]
    shared_corpus_database_url: str = ""

    # Workers
    worker_poll_seconds: int = 5

    # Scheduler (Component C) — deterministic reminders/reports [C-IV]
    scheduler_reminder_hour: int = 8  # firm-local hour for the daily reminder pass
    waha_session: str = "default"  # WAHA Plus session name (per-firm tenant id)
    # Optional shared secret for the inbound WAHA webhook. When set, the webhook
    # rejects calls whose X-Webhook-Token header does not match. [C-I]
    waha_webhook_token: str = ""

    # CORS
    cors_origins: str = "*"

    # ── Paymob (Egypt billing) — WP-S3 ──
    paymob_api_key: str = ""
    paymob_integration_id: str = ""
    paymob_iframe_id: str = ""
    paymob_hmac_secret: str = ""  # SECRET: webhook verification [C-III]


@lru_cache
def get_settings() -> Settings:
    return Settings()
