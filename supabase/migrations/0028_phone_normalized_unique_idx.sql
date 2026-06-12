-- 0028: Enforce uniqueness on digit-normalized phone to prevent non-deterministic
-- WhatsApp webhook binding when two users share the same digits in different formats.
-- The existing unique constraint is on the raw phone string; this adds a functional
-- unique index on the normalized (digits-only) representation.

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_digits_unique
    ON users (regexp_replace(coalesce(phone, ''), '\D', '', 'g'))
    WHERE phone IS NOT NULL AND phone != '';
