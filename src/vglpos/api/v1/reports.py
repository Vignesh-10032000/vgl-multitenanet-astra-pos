"""Thin operational and statutory reporting API routes."""

from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, Response, current_app, g, send_file
from sqlalchemy.orm import Session

from vglpos.api.v1.http import model_response, parse_body, parse_query
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.reports import (
    DailySummaryQuery,
    DailySummaryResponse,
    DateRangeQuery,
    Gstr1Response,
    InventoryValuationQuery,
    InventoryValuationResponse,
    ReportJobCreateRequest,
    ReportJobResponse,
    RevenueQuery,
    RevenueSeriesResponse,
)
from vglpos.api.v1.serializers import (
    daily_summary_response,
    gstr1_response,
    inventory_valuation_response,
    revenue_series_response,
)
from vglpos.domain.models import ReportJob
from vglpos.extensions import db, limiter
from vglpos.security.decorators import require_permission
from vglpos.services.cache_service import dashboard_key, get_mapping, set_mapping
from vglpos.services.report_job_service import ReportJobService
from vglpos.services.report_service import ReportService
from vglpos.tasks.reports import generate_report_artifact

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
    key = dashboard_key(company_id=g.company_id, branch_id=g.branch_id, on_date=query.on_date)
    cached = get_mapping(key)
    if cached is not None:
        return model_response(DailySummaryResponse.model_validate(cached))
    with Session(db.engine) as session:
        summary = ReportService(session, g.company_id).daily_summary(
            query.on_date, branch_id=g.branch_id
        )
        result = daily_summary_response(summary)
        set_mapping(key, result.model_dump(mode="json"))
        return model_response(result)


@reports_bp.get("/revenue")
@require_permission("report.view")
@limiter.limit("20 per minute", key_func=_user_rate_key)
@documented(
    summary="Get a gap-filled daily revenue series",
    query_model=RevenueQuery,
    response_model=RevenueSeriesResponse,
)
def revenue() -> tuple[Response, int]:
    query = parse_query(RevenueQuery)
    end_date = date.today()
    start_date = end_date - timedelta(days=query.days - 1)
    with Session(db.engine) as session:
        rows = ReportService(session, g.company_id).revenue_series(
            start_date, end_date, branch_id=g.branch_id
        )
        return model_response(revenue_series_response(rows))


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


def _report_job_response(job: ReportJob) -> ReportJobResponse:
    base = ReportJobResponse(
        id=job.id,
        report_name=job.report_name,
        output_format=job.output_format,
        parameters=job.parameters,
        status=job.status,
        error_message=job.error_message,
        completed_at=job.completed_at,
        created_at=job.created_at,
        download_url=None,
    )
    if base.status != "COMPLETED":
        return base
    return base.model_copy(update={"download_url": f"/api/v1/reports/jobs/{base.id}/download"})


@reports_bp.post("/jobs")
@require_permission("report.view", "report.export", require_all=True)
@idempotent
@limiter.limit("10 per minute", key_func=_user_rate_key)
@documented(
    summary="Queue a downloadable report artifact",
    request_model=ReportJobCreateRequest,
    response_model=ReportJobResponse,
    success_status=202,
)
def create_report_job() -> tuple[Response, int]:
    body = parse_body(ReportJobCreateRequest)
    with Session(db.engine) as session:
        job = ReportJobService(session, g.company_id).create(
            requested_by=g.user_id,
            report_name=body.report_name,
            output_format=body.output_format,
            parameters=body.parameters,
        )
        generate_report_artifact.delay(company_id=g.company_id, job_id=job.id)
        return model_response(_report_job_response(job), status=202)


@reports_bp.get("/jobs/<int:job_id>")
@require_permission("report.view")
@documented(summary="Get report job status", response_model=ReportJobResponse)
def report_job_status(job_id: int) -> tuple[Response, int]:
    with Session(db.engine) as session:
        job = ReportJobService(session, g.company_id).get(job_id)
        return model_response(_report_job_response(job))


@reports_bp.get("/jobs/<int:job_id>/download")
@require_permission("report.view", "report.export", require_all=True)
def download_report_job(job_id: int) -> Response:
    with Session(db.engine) as session:
        service = ReportJobService(session, g.company_id)
        job = service.get(job_id)
        path, content_type = service.artifact(
            job_id, str(current_app.config["REPORT_ARTIFACT_DIR"])
        )
        suffix = path.suffix.removeprefix(".")
        return send_file(
            path,
            mimetype=content_type,
            as_attachment=True,
            download_name=f"{job.report_name.lower()}-{job.id}.{suffix}",
        )
