-- 0011_firms_and_subscriptions.sql
-- SaaS conversion (WP-S1): tenants + billing. [constitution v2: C-I = RLS isolation]

create table firms (
    id            uuid primary key default gen_random_uuid(),
    name          text not null,
    slug          text not null unique,
    status        text not null default 'trial'
                  check (status in ('trial','active','past_due','suspended','cancelled')),
    trial_ends_at timestamptz not null default now() + interval '14 days',
    created_at    timestamptz not null default now()
);

create table subscriptions (
    id                   uuid primary key default gen_random_uuid(),
    firm_id              uuid not null references firms(id),
    plan                 text not null check (plan in ('basic','pro','enterprise')),
    provider             text not null check (provider in ('paymob','paddle','manual')),
    provider_customer_id text,
    provider_sub_id      text,
    current_period_end   timestamptz,
    status               text not null default 'incomplete'
                         check (status in ('incomplete','trialing','active','past_due','cancelled')),
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);
create index idx_subscriptions_firm on subscriptions(firm_id);
create trigger trg_subscriptions_updated_at before update on subscriptions
    for each row execute function set_updated_at();

-- Immutable provider webhook inbox (idempotency + audit). [C-III]
create table billing_events (
    id           uuid primary key default gen_random_uuid(),
    provider     text not null,
    provider_ref text not null,
    payload      jsonb not null,
    processed_at timestamptz,
    received_at  timestamptz not null default now(),
    unique (provider, provider_ref)
);

-- Audit the new tables (same generic trigger). [C-III]
do $$
declare t text;
begin
    foreach t in array array['firms','subscriptions','billing_events'] loop
        execute format(
            'create trigger trg_audit_%s after insert or update or delete on %I
             for each row execute function audit_trigger()', t, t);
    end loop;
end $$;

grant select on firms, subscriptions, billing_events to app_user;
-- writes are service-context only (signup + billing webhooks).
