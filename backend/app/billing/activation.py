"""Shared subscription activation (feature 003 T023).

``activate_subscription`` is the single code path that marks a firm as active
after a successful payment — whether from the Paymob webhook or an operator
manual payment.  Both callers pass the same asyncpg connection so the
activation is always within the caller's transaction context. [C-III]
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


async def activate_subscription(
    conn: asyncpg.Connection,
    firm_id: UUID,
    plan: str,
    period_end: datetime | None = None,
    *,
    provider: str = "manual",
    provider_sub_id: str | None = None,
) -> None:
    """Update subscriptions + firms to active status.

    Args:
        conn:            asyncpg connection (caller owns transaction context).
        firm_id:         Target firm.
        plan:            Subscription plan code (basic / pro / enterprise).
        period_end:      Optional explicit period-end; defaults to now() + 1 month.
        provider:        Payment provider tag (default 'manual' for operator payments).
        provider_sub_id: Provider-side subscription/transaction id, if known.
    """
    period_sql = "$4" if period_end is not None else "now() + interval '1 month'"
    params: list = [firm_id, plan, provider or "manual"]
    if period_end is not None:
        params.append(period_end)
    if provider_sub_id is not None:
        params.append(provider_sub_id)

    sub_id_sql = f", provider_sub_id = ${len(params)}" if provider_sub_id is not None else ""

    await conn.execute(
        f"""
        UPDATE subscriptions
           SET plan = $2,
               provider = $3,
               status = 'active',
               current_period_end = {period_sql},
               updated_at = now()
               {sub_id_sql}
         WHERE firm_id = $1
        """,
        *params,
    )
    await conn.execute(
        "UPDATE firms SET status = 'active' WHERE id = $1",
        firm_id,
    )
    logger.info("billing:activate: firm %s activated on plan %s via %s", firm_id, plan, provider)
