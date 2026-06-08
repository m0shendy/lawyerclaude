-- 0024: Add feature_client_portal flag to firm_settings
-- Controlled toggle for the client-facing portal feature.
-- Default FALSE — managers opt-in per-firm via Settings UI.
ALTER TABLE firm_settings
    ADD COLUMN IF NOT EXISTS feature_client_portal BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN firm_settings.feature_client_portal IS
    'Toggle for client portal feature. When FALSE the /portal/* routes are '
    'inaccessible to portal-role tokens.';
