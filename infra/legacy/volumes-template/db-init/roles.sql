-- =============================================================================
-- Internal Supabase role passwords  [provisioned per firm]
-- =============================================================================
-- The supabase/postgres image CREATES the internal login roles but leaves their
-- passwords unset. GoTrue / PostgREST / Storage all connect using
-- ${POSTGRES_PASSWORD}, so without this script they fail SASL auth (28P01) and
-- crash-loop. This runs during DB init as the bootstrap SUPERUSER (the only role
-- allowed to modify these reserved roles), reading the password from the
-- container environment — no secret is stored in this file.
--
-- Mounted by infra/docker-compose.yml at:
--   /docker-entrypoint-initdb.d/init-scripts/99-roles.sql
-- It therefore runs AFTER the image's own role-creation migrations.
-- =============================================================================

\set pgpass `echo "$POSTGRES_PASSWORD"`

ALTER USER authenticator          WITH PASSWORD :'pgpass';
ALTER USER supabase_auth_admin    WITH PASSWORD :'pgpass';
ALTER USER supabase_storage_admin WITH PASSWORD :'pgpass';
ALTER USER pgbouncer              WITH PASSWORD :'pgpass';
