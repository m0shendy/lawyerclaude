-- 0001_extensions.sql
-- Enable required extensions for the per-firm instance. [C-XII]
-- pgvector powers RAG over document_chunks; pgcrypto provides gen_random_uuid().

create extension if not exists vector;
create extension if not exists pgcrypto;

-- Application database role (the backend connects as app_user; the provision
-- script sets its password — never a default). [C-XI]
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_user') then
    create role app_user login;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end
$$;

grant usage on schema public to app_user, anon, service_role;
