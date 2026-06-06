"""Daily report endpoint (T074 backend). [C-IV]

``GET /reports/daily`` — **manager only**. Assembles today's report from audited
data (Component C, deterministic) and returns it for the in-app Reports view. The
LLM phrasing step is best-effort: if the firm has an LLM key the sections carry
reworded Arabic prose, otherwise a deterministic prose fallback. Either way the
``items`` are the authoritative, audit-grounded facts. [C-IV]

This endpoint never sends WhatsApp and never writes ``reports_log`` — that is the
scheduler worker's job (``generate_and_send_daily_reports``). Reading the report
is side-effect free.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.db import Db
from app.core.rbac import MANAGER, require_roles
from app.core.security import CurrentUser
from app.scheduler.reports import (
    _HEADING_TODAY,
    _HEADING_TOMORROW,
    _model_from_firm,
    assemble_daily_report,
    phrase_section,
)

logger = logging.getLogger(__name__)

router = APIRouter()

ManagerDep = Depends(require_roles(MANAGER))


class ReportSection(BaseModel):
    heading: str
    prose: str
    items: list[dict[str, Any]]


class DailyReportResponse(BaseModel):
    report_date: str
    what_happened: ReportSection
    tomorrow: ReportSection


@router.get("/reports/daily", response_model=DailyReportResponse)
async def get_daily_report(
    conn: Db,
    _manager: Annotated[CurrentUser, ManagerDep],
) -> DailyReportResponse:
    report = await assemble_daily_report(conn)

    firm = await conn.fetchrow(
        "SELECT llm_api_key, embedding_config FROM firm_settings LIMIT 1"
    )
    api_key = firm["llm_api_key"] if firm else None
    model = _model_from_firm(firm)

    today_prose = await phrase_section(
        _HEADING_TODAY, report.what_happened, api_key=api_key, model=model
    )
    tomorrow_prose = await phrase_section(
        _HEADING_TOMORROW, report.tomorrow, api_key=api_key, model=model
    )

    return DailyReportResponse(
        report_date=report.report_date.isoformat(),
        what_happened=ReportSection(
            heading=_HEADING_TODAY,
            prose=today_prose,
            items=[it.as_dict() for it in report.what_happened],
        ),
        tomorrow=ReportSection(
            heading=_HEADING_TOMORROW,
            prose=tomorrow_prose,
            items=[it.as_dict() for it in report.tomorrow],
        ),
    )
