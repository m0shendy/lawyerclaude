-- 0010_service_role.sql
-- Dedicated BYPASSRLS login role for background workers / system contexts.
--
-- The API connects as app_user (RLS-enforced, see 0007). The deterministic
-- pipeline and scheduler workers run with NO in-instance user identity, yet
-- legitimately operate across all rows (claim any pending document, write
-- chunks, etc.). RLS would otherwise hide every row from them. They therefore
-- connect as app_service: app_user's table grants PLUS the BYPASSRLS attribute.
-- It is NOT a superuser. Its password is set by the provision script, same as
-- app_user (the backend reads SERVICE_DATABASE_URL).

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'app_service') then
        create role app_service login bypassrls;
    else
        alter role app_service with login bypassrls;
    end if;
end $$;

-- Inherit app_user's table privileges (RLS is skipped via BYPASSRLS on the role).
grant app_user to app_service;
