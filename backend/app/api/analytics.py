"""Financial Analytics & Reporting endpoints (Modules F and H).

Module F — Financial Dashboard (partner_manager only):
  GET /analytics/revenue               — monthly/weekly/lawyer revenue summary
  GET /analytics/aging                 — accounts receivable aging buckets
  GET /analytics/lawyer-productivity   — hours, billable hours, utilization
  GET /analytics/case-profitability    — per-case margin

Module H — Advanced Reporting:
  GET /reports/case-summary            — case status breakdown
  GET /reports/deadline-compliance     — deadline hit/miss rate
  GET /reports/workload                — tasks + hearings + deadlines per lawyer
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.db import Db
from app.core.errors import ApiError
from app.core.rbac import MANAGER, require_roles
from app.core.security import CurrentUserDep

logger = logging.getLogger(__name__)

router = APIRouter()

ManagerOnly = Annotated[object, Depends(require_roles(MANAGER))]


# ── GET /analytics/revenue ────────────────────────────────────────────────────

class RevenuePeriod(BaseModel):
    period: str
    billed_egp: Decimal
    collected_egp: Decimal
    outstanding_egp: Decimal


@router.get("/analytics/revenue", response_model=list[RevenuePeriod])
async def revenue_summary(
    _: ManagerOnly,
    conn: Db,
    from_date: date = Query(default_factory=lambda: date.today().replace(day=1)),
    to_date: date = Query(default_factory=date.today),
    group_by: Literal["month", "week", "lawyer"] = Query("month"),
) -> list[RevenuePeriod]:
    if group_by == "month":
        rows = await conn.fetch(
            """
            SELECT
                to_char(i.issue_date, 'YYYY-MM')      AS period,
                coalesce(sum(i.total_egp), 0)          AS billed_egp,
                coalesce(sum(p_paid.paid), 0)          AS collected_egp,
                coalesce(sum(i.total_egp), 0)
                  - coalesce(sum(p_paid.paid), 0)      AS outstanding_egp
            FROM invoices i
            LEFT JOIN LATERAL (
                SELECT sum(amount_egp) AS paid
                FROM payments WHERE invoice_id = i.id
            ) p_paid ON true
            WHERE i.issue_date BETWEEN $1 AND $2
              AND i.status NOT IN ('cancelled','draft')
            GROUP BY to_char(i.issue_date, 'YYYY-MM')
            ORDER BY 1
            """,
            from_date, to_date,
        )
    elif group_by == "week":
        rows = await conn.fetch(
            """
            SELECT
                to_char(date_trunc('week', i.issue_date), 'IYYY-IW') AS period,
                coalesce(sum(i.total_egp), 0)   AS billed_egp,
                coalesce(sum(p_paid.paid), 0)   AS collected_egp,
                coalesce(sum(i.total_egp), 0)
                  - coalesce(sum(p_paid.paid), 0) AS outstanding_egp
            FROM invoices i
            LEFT JOIN LATERAL (
                SELECT sum(amount_egp) AS paid FROM payments WHERE invoice_id = i.id
            ) p_paid ON true
            WHERE i.issue_date BETWEEN $1 AND $2
              AND i.status NOT IN ('cancelled','draft')
            GROUP BY date_trunc('week', i.issue_date)
            ORDER BY date_trunc('week', i.issue_date)
            """,
            from_date, to_date,
        )
    else:  # group_by == "lawyer"
        rows = await conn.fetch(
            """
            SELECT
                u.full_name                        AS period,
                coalesce(sum(te.amount_egp), 0)    AS billed_egp,
                coalesce(sum(p_paid.paid), 0)      AS collected_egp,
                coalesce(sum(te.amount_egp), 0)
                  - coalesce(sum(p_paid.paid), 0)  AS outstanding_egp
            FROM time_entries te
            JOIN users u ON te.user_id = u.id
            LEFT JOIN invoices i ON te.invoice_id = i.id
            LEFT JOIN LATERAL (
                SELECT sum(amount_egp) AS paid
                FROM payments WHERE invoice_id = i.id
            ) p_paid ON true
            WHERE te.date BETWEEN $1 AND $2
              AND te.is_billable = true
            GROUP BY u.id, u.full_name
            ORDER BY billed_egp DESC
            """,
            from_date, to_date,
        )

    return [RevenuePeriod(**dict(r)) for r in rows]


# ── GET /analytics/aging ─────────────────────────────────────────────────────

class AgingBucket(BaseModel):
    bucket: str
    count: int
    total_egp: Decimal


@router.get("/analytics/aging", response_model=list[AgingBucket])
async def aging_report(_: ManagerOnly, conn: Db) -> list[AgingBucket]:
    today = date.today()
    rows = await conn.fetch(
        """
        WITH paid_totals AS (
            SELECT invoice_id, sum(amount_egp) AS paid
            FROM payments GROUP BY invoice_id
        ),
        outstanding AS (
            SELECT
                i.id, i.due_date, i.total_egp,
                coalesce(pt.paid, 0) AS paid,
                i.total_egp - coalesce(pt.paid, 0) AS balance,
                ($1 - i.due_date) AS days_overdue
            FROM invoices i
            LEFT JOIN paid_totals pt ON i.id = pt.invoice_id
            WHERE i.status NOT IN ('paid','cancelled','draft')
              AND i.total_egp - coalesce(pt.paid, 0) > 0
        )
        SELECT
            CASE
                WHEN days_overdue <= 0  THEN 'current'
                WHEN days_overdue <= 30 THEN '1-30'
                WHEN days_overdue <= 60 THEN '31-60'
                WHEN days_overdue <= 90 THEN '61-90'
                ELSE '90+'
            END AS bucket,
            count(*)              AS count,
            sum(balance)          AS total_egp
        FROM outstanding
        GROUP BY 1
        ORDER BY
            CASE bucket
                WHEN 'current' THEN 0 WHEN '1-30' THEN 1
                WHEN '31-60' THEN 2 WHEN '61-90' THEN 3 ELSE 4
            END
        """,
        today,
    )
    return [AgingBucket(**dict(r)) for r in rows]


# ── GET /analytics/lawyer-productivity ───────────────────────────────────────

class LawyerProductivity(BaseModel):
    user_id: UUID
    name: str
    hours_logged: Decimal
    billable_hours: Decimal
    billed_egp: Decimal
    collected_egp: Decimal
    utilization_rate: Decimal  # billable / total


@router.get("/analytics/lawyer-productivity", response_model=list[LawyerProductivity])
async def lawyer_productivity(
    _: ManagerOnly,
    conn: Db,
    from_date: date = Query(default_factory=lambda: date.today().replace(day=1)),
    to_date: date = Query(default_factory=date.today),
) -> list[LawyerProductivity]:
    rows = await conn.fetch(
        """
        SELECT
            u.id                                                   AS user_id,
            u.full_name                                            AS name,
            round(sum(te.duration_minutes)::numeric / 60, 2)      AS hours_logged,
            round(sum(CASE WHEN te.is_billable THEN te.duration_minutes ELSE 0 END)::numeric / 60, 2)
                                                                   AS billable_hours,
            coalesce(sum(CASE WHEN te.is_billable THEN te.amount_egp ELSE 0 END), 0)
                                                                   AS billed_egp,
            coalesce((
                SELECT sum(p.amount_egp)
                FROM payments p
                JOIN invoices inv ON p.invoice_id = inv.id
                JOIN time_entries te2 ON te2.invoice_id = inv.id
                WHERE te2.user_id = u.id AND te2.date BETWEEN $1 AND $2
            ), 0)                                                  AS collected_egp,
            CASE
                WHEN sum(te.duration_minutes) = 0 THEN 0
                ELSE round(
                    sum(CASE WHEN te.is_billable THEN te.duration_minutes ELSE 0 END)::numeric
                    / sum(te.duration_minutes) * 100, 1
                )
            END                                                    AS utilization_rate
        FROM time_entries te
        JOIN users u ON te.user_id = u.id
        WHERE te.date BETWEEN $1 AND $2
        GROUP BY u.id, u.full_name
        ORDER BY billable_hours DESC
        """,
        from_date, to_date,
    )
    return [LawyerProductivity(**dict(r)) for r in rows]


# ── GET /analytics/case-profitability ────────────────────────────────────────

class CaseProfitability(BaseModel):
    case_id: UUID
    case_number: str | None
    title: str
    total_billed: Decimal
    total_collected: Decimal
    time_value: Decimal
    margin: Decimal  # collected - time_value


@router.get("/analytics/case-profitability", response_model=list[CaseProfitability])
async def case_profitability(
    _: ManagerOnly,
    conn: Db,
    case_id: UUID | None = Query(None),
) -> list[CaseProfitability]:
    where = "AND c.id = $1" if case_id else ""
    params = [case_id] if case_id else []
    rows = await conn.fetch(
        f"""
        SELECT
            c.id           AS case_id,
            c.case_number,
            c.title,
            coalesce(inv_totals.total_billed, 0)    AS total_billed,
            coalesce(pay_totals.total_collected, 0) AS total_collected,
            coalesce(te_totals.time_value, 0)       AS time_value,
            coalesce(pay_totals.total_collected, 0)
              - coalesce(te_totals.time_value, 0)   AS margin
        FROM cases c
        LEFT JOIN LATERAL (
            SELECT sum(total_egp) AS total_billed
            FROM invoices WHERE case_id = c.id AND status NOT IN ('cancelled','draft')
        ) inv_totals ON true
        LEFT JOIN LATERAL (
            SELECT sum(p.amount_egp) AS total_collected
            FROM payments p
            JOIN invoices i ON p.invoice_id = i.id
            WHERE i.case_id = c.id
        ) pay_totals ON true
        LEFT JOIN LATERAL (
            SELECT sum(amount_egp) AS time_value
            FROM time_entries WHERE case_id = c.id AND is_billable = true
        ) te_totals ON true
        WHERE true {where}
        ORDER BY total_billed DESC NULLS LAST
        LIMIT 200
        """,
        *params,
    )
    return [CaseProfitability(**dict(r)) for r in rows]


# ── Module H: Advanced Reporting ─────────────────────────────────────────────

class CaseSummaryRow(BaseModel):
    status: str
    count: int
    case_type: str | None


@router.get("/reports/case-summary", response_model=list[CaseSummaryRow])
async def case_summary_report(
    _: ManagerOnly,
    conn: Db,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    status: str | None = Query(None),
) -> list[CaseSummaryRow]:
    conditions = []
    params: list = []
    if from_date:
        params.append(from_date)
        conditions.append(f"created_at::date >= ${len(params)}")
    if to_date:
        params.append(to_date)
        conditions.append(f"created_at::date <= ${len(params)}")
    if status:
        params.append(status)
        conditions.append(f"status = ${len(params)}")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await conn.fetch(
        f"SELECT status, case_type, count(*)::int AS count FROM cases {where} GROUP BY status, case_type ORDER BY count DESC",
        *params,
    )
    return [CaseSummaryRow(**dict(r)) for r in rows]


class DeadlineComplianceRow(BaseModel):
    user_id: UUID | None
    user_name: str | None
    total_deadlines: int
    met_on_time: int
    missed: int
    compliance_rate: Decimal


@router.get("/reports/deadline-compliance", response_model=list[DeadlineComplianceRow])
async def deadline_compliance_report(
    _: ManagerOnly,
    conn: Db,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    user_id: UUID | None = Query(None),
) -> list[DeadlineComplianceRow]:
    conditions = ["d.due_date IS NOT NULL"]
    params: list = []
    if from_date:
        params.append(from_date)
        conditions.append(f"d.due_date >= ${len(params)}")
    if to_date:
        params.append(to_date)
        conditions.append(f"d.due_date <= ${len(params)}")
    if user_id:
        params.append(user_id)
        conditions.append(f"ca.user_id = ${len(params)}")
    where = " AND ".join(conditions)

    rows = await conn.fetch(
        f"""
        SELECT
            ca.user_id,
            u.full_name AS user_name,
            count(distinct d.id)::int AS total_deadlines,
            count(distinct d.id) FILTER (
                WHERE d.due_date >= current_date OR d.due_date IS NULL
            )::int AS met_on_time,
            count(distinct d.id) FILTER (
                WHERE d.due_date < current_date
            )::int AS missed,
            CASE WHEN count(distinct d.id) = 0 THEN 100
                 ELSE round(
                     count(distinct d.id) FILTER (WHERE d.due_date >= current_date)::numeric
                     / count(distinct d.id) * 100, 1
                 )
            END AS compliance_rate
        FROM deadlines d
        JOIN cases c ON d.case_id = c.id
        JOIN case_assignments ca ON ca.case_id = c.id
        JOIN users u ON ca.user_id = u.id
        WHERE {where}
        GROUP BY ca.user_id, u.full_name
        ORDER BY compliance_rate ASC
        """,
        *params,
    )
    return [DeadlineComplianceRow(**dict(r)) for r in rows]


class WorkloadRow(BaseModel):
    user_id: UUID
    user_name: str
    open_tasks: int
    upcoming_hearings: int
    pending_deadlines: int


@router.get("/reports/workload", response_model=list[WorkloadRow])
async def workload_report(
    _: ManagerOnly,
    conn: Db,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
) -> list[WorkloadRow]:
    end = to_date or (date.today() + timedelta(days=30))
    start = from_date or date.today()

    rows = await conn.fetch(
        """
        SELECT
            u.id AS user_id,
            u.full_name AS user_name,
            (SELECT count(*) FROM tasks t
             WHERE t.assigned_to = u.id AND t.status IN ('open','in_progress'))::int AS open_tasks,
            (SELECT count(*) FROM hearings h
             WHERE h.assigned_lawyer_id = u.id
               AND h.status = 'scheduled'
               AND h.hearing_date::date BETWEEN $1 AND $2)::int AS upcoming_hearings,
            (SELECT count(*) FROM deadlines d
             JOIN case_assignments ca2 ON ca2.case_id = d.case_id AND ca2.user_id = u.id
             WHERE d.due_date BETWEEN $1 AND $2)::int AS pending_deadlines
        FROM users u
        WHERE u.status = 'active'
          AND u.role IN ('lawyer','paralegal')
        ORDER BY (open_tasks + upcoming_hearings + pending_deadlines) DESC
        """,
        start, end,
    )
    return [WorkloadRow(**dict(r)) for r in rows]
