# Legacy per-firm infrastructure (constitution v1)

This directory holds the v1 deployment model: one Docker stack + self-hosted
Supabase **per firm** (Traefik routing, per-firm provisioning, local backups).

Retired in constitution v2.0.0 when the product became a multi-tenant SaaS on
Supabase Cloud (see `docs/SAAS_RUNBOOK.md`). Retained intentionally:

* A future **Enterprise tier** may sell dedicated single-firm instances; this
  stack is the starting point for that offering.
* The provisioning and hardening scripts document the original security
  baseline (Principle XI) and remain useful reference material.

Nothing here is wired into CI or the SaaS deployment. Do not "fix" code in
this tree to track the multi-tenant schema — a dedicated instance would run
the same migrations (a single-firm database is just a tenant count of one).
