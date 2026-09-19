"""Thin operational and statutory reporting API routes."""

from __future__ import annotations

from flask import Blueprint, Response, g
from sqlalchemy.orm import Session

from vglpos.api.v1.http import model_response, parse_query
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.reports import (
    DailySummaryQuery,
    DailySummaryResponse,
    DateRangeQuery,
    Gstr1Response,
    InventoryValuationQuery,
    InventoryValuationResponse,
)
from vglpos.api.v1.serializers import (
    daily_summary_response,
    gstr1_response,
    inventory_valuation_response,
)
from vglpos.extensions import db, limiter
from vglpos.security.decorators import require_permission
from vglpos.services.report_service import ReportService

reports_bp = Blueprint("reports", __name__, url_prefix="/api/v1/reports")


def _user_rate_key() -> str:
    return f"{g.company_id}:{g.user_id}"


@reports_bp.get("/daily-summary")
@require_permission("report.view")
@limiter.limit("20 per minute", key_func=_user_rate_key)
@documented(
    summary="Get the daily reconciled sales summary",
    query_model=DailySummaryQuery,
    response_model=DailySummaryResponse,
)
def daily_summary() -> tuple[Response, int]:
    query = parse_query(DailySummaryQuery)
    with Session(db.engine) as session:
        summary = ReportService(session, g.company_id).daily_summary(
            query.on_date, branch_id=g.branch_id
        )
        return model_response(daily_summary_response(summary))


@reports_bp.get("/gstr1")
@require_permission("report.gst", "report.export", require_all=True)
@limiter.limit("20 per minute", key_func=_user_rate_key)
@limiter.limit("5 per hour", key_func=_user_rate_key)
@documented(
    summary="Export GSTR-1 outward-supply data",
    query_model=DateRangeQuery,
    response_model=Gstr1Response,
)
def gstr1() -> tuple[Response, int]:
    query = parse_query(DateRangeQuery)
    with Session(db.engine) as session:
        service = ReportService(session, g.company_id)
        rows = service.gstr1_data(query.start_date, query.end_date, branch_id=g.branch_id)
        service.record_export(
            user_id=g.user_id,
            report_name="GSTR1",
            start_date=query.start_date,
            end_date=query.end_date,
            output_format="JSON",
        )
        return model_response(gstr1_response(rows))


@reports_bp.get("/inventory-valuation")
@require_permission("report.view")
@limiter.limit("20 per minute", key_func=_user_rate_key)
@documented(
    summary="Value inventory by weighted average or FIFO",
    query_model=InventoryValuationQuery,
    response_model=InventoryValuationResponse,
)
def inventory_valuation() -> tuple[Response, int]:
    query = parse_query(InventoryValuationQuery)
    with Session(db.engine) as session:
        valuation = ReportService(session, g.company_id).inventory_valuation(
            method=query.method, branch_id=g.branch_id
        )
        return model_response(inventory_valuation_response(valuation))
