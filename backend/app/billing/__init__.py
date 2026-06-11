"""Billing — provider-agnostic subscription layer (WP-S3).

``plans`` defines what is sold; ``base.BillingProvider`` is the interface every
payment provider implements (Paymob first; Paddle later for non-Egyptian
firms).  Amounts are reconciled server-side against the plan table — amounts
arriving in webhooks are NEVER trusted as the source of truth. [C-III]
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    code: str
    name_ar: str
    monthly_egp: int  # whole EGP
    max_users: int


PLANS: dict[str, Plan] = {
    "basic": Plan("basic", "الأساسية", monthly_egp=1500, max_users=5),
    "pro": Plan("pro", "الاحترافية", monthly_egp=3000, max_users=15),
    "enterprise": Plan("enterprise", "المؤسسات", monthly_egp=6000, max_users=999),
}
