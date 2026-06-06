-- 0009_storage_bucket.sql
-- Ensure the private "documents" storage bucket exists for document uploads.
-- The Storage API service creates the `storage` schema on first boot; this
-- migration is guarded so it is a no-op if Storage hasn't initialised yet
-- (the bucket can also be created via the Storage admin API). The bucket id
-- must match STORAGE_BUCKET in the firm .env (default: documents). Private
-- bucket — objects are served only via the service-role key from the backend.

do $$
begin
    if to_regclass('storage.buckets') is not null then
        insert into storage.buckets (id, name, public)
        values ('documents', 'documents', false)
        on conflict (id) do nothing;
    end if;
end $$;
