"""Thin Phase 9 compliance administration and e-way bill routes."""

from __future__ import annotations

from flask import Blueprint, Response, g
from sqlalchemy.orm import Session

from vglpos.api.v1.http import model_response, parse_body, parse_query
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.compliance import (
    ComplianceAlertResponse,
    ComplianceSettingsRequest,
    ComplianceSettingsResponse,
    EInvoiceCancelRequest,
    EInvoiceListResponse,
    EInvoiceQuery,
    EInvoiceResponse,
    EmptyCommandRequest,
    EWayBillListResponse,
    EWayBillRequest,
    EWayBillResponse,
    InvoiceTemplateListResponse,
    InvoiceTemplateRequest,
    InvoiceTemplateResponse,
    ReconciliationIssueResponse,
    ReconciliationResponse,
)
from vglpos.extensions import db, limiter
from vglpos.security.decorators import require_permission
from vglpos.services.einvoice_service import EInvoiceService, EWayBillCommand, EWayBillService
from vglpos.services.invoice_compliance_service import (
    ComplianceSettingsCommand,
    InvoiceComplianceService,
    InvoiceTemplateCommand,
)
from vglpos.tasks.compliance import process_einvoice, process_eway_bill

compliance_bp = Blueprint("compliance", __name__, url_prefix="/api/v1/compliance")


def _user_rate_key() -> str:
    return f"{g.company_id}:{g.user_id}"


@compliance_bp.get("/e-invoices")
@require_permission("einvoice.view")
@documented(
    summary="List e-invoice queue and dead-letter records",
    query_model=EInvoiceQuery,
    response_model=EInvoiceListResponse,
)
def list_einvoices() -> tuple[Response, int]:
    query = parse_query(EInvoiceQuery)
    with Session(db.engine) as session:
        records = EInvoiceService(session, g.company_id).list(
            status=query.status, limit=query.limit
        )
        return model_response(
            EInvoiceListResponse(items=[EInvoiceResponse.model_validate(row) for row in records])
        )


@compliance_bp.post("/e-invoices/<int:record_id>/retry")
@require_permission("einvoice.retry")
@idempotent
@limiter.limit("20 per hour", key_func=_user_rate_key)
@documented(
    summary="Retry a reviewed e-invoice failure",
    request_model=EmptyCommandRequest,
    response_model=EInvoiceResponse,
    success_status=202,
)
def retry_einvoice(record_id: int) -> tuple[Response, int]:
    parse_body(EmptyCommandRequest)
    with Session(db.engine) as session:
        record = EInvoiceService(session, g.company_id).retry(record_id, user_id=g.user_id)
        record_id = record.id
        response = EInvoiceResponse.model_validate(record)
    process_einvoice.delay(company_id=g.company_id, record_id=record_id)
    return model_response(response, status=202)


@compliance_bp.post("/e-invoices/<int:record_id>/cancel")
@require_permission("einvoice.cancel")
@idempotent
@limiter.limit("20 per hour", key_func=_user_rate_key)
@documented(
    summary="Queue IRN cancellation inside the 24-hour window",
    request_model=EInvoiceCancelRequest,
    response_model=EInvoiceResponse,
    success_status=202,
)
def cancel_einvoice(record_id: int) -> tuple[Response, int]:
    body = parse_body(EInvoiceCancelRequest)
    with Session(db.engine) as session:
        record = EInvoiceService(session, g.company_id).request_cancellation(
            record_id, user_id=g.user_id, reason=body.reason
        )
        record_id = record.id
        response = EInvoiceResponse.model_validate(record)
    process_einvoice.delay(company_id=g.company_id, record_id=record_id)
    return model_response(response, status=202)


@compliance_bp.get("/alerts")
@require_permission("einvoice.view")
@documented(summary="Inspect e-invoice queue health", response_model=ComplianceAlertResponse)
def compliance_alerts() -> tuple[Response, int]:
    with Session(db.engine) as session:
        alert = EInvoiceService(session, g.company_id).alert()
        return model_response(ComplianceAlertResponse.model_validate(alert))


@compliance_bp.get("/reconciliation")
@require_permission("einvoice.view")
@documented(
    summary="Compare qualifying sales with generated IRNs",
    response_model=ReconciliationResponse,
)
def reconciliation() -> tuple[Response, int]:
    with Session(db.engine) as session:
        issues = EInvoiceService(session, g.company_id).reconciliation()
        return model_response(
            ReconciliationResponse(
                items=[ReconciliationIssueResponse.model_validate(row) for row in issues]
            )
        )


@compliance_bp.post("/sales/<int:sale_id>/eway-bills")
@require_permission("eway.generate")
@idempotent
@limiter.limit("20 per hour", key_func=_user_rate_key)
@documented(
    summary="Queue an applicable outward e-way bill",
    request_model=EWayBillRequest,
    response_model=EWayBillResponse,
    success_status=202,
)
def create_eway_bill(sale_id: int) -> tuple[Response, int]:
    body = parse_body(EWayBillRequest)
    with Session(db.engine) as session:
        record = EWayBillService(session, g.company_id).create(
            EWayBillCommand(
                company_id=g.company_id,
                sale_id=sale_id,
                user_id=g.user_id,
                **body.model_dump(),
            )
        )
        record_id = record.id
        response = EWayBillResponse.model_validate(record)
    if response.status == "PENDING":
        process_eway_bill.delay(company_id=g.company_id, record_id=record_id)
    return model_response(response, status=202)


@compliance_bp.get("/eway-bills")
@require_permission("einvoice.view")
@documented(summary="List e-way bill jobs", response_model=EWayBillListResponse)
def list_eway_bills() -> tuple[Response, int]:
    with Session(db.engine) as session:
        records = EWayBillService(session, g.company_id).list()
        return model_response(
            EWayBillListResponse(items=[EWayBillResponse.model_validate(row) for row in records])
        )


@compliance_bp.get("/settings")
@require_permission("einvoice.view")
@documented(summary="Read tenant compliance settings", response_model=ComplianceSettingsResponse)
def get_settings() -> tuple[Response, int]:
    with Session(db.engine) as session:
        company = InvoiceComplianceService(session, g.company_id).settings()
        return model_response(ComplianceSettingsResponse.model_validate(company))


@compliance_bp.put("/settings")
@require_permission("settings.manage")
@idempotent
@documented(
    summary="Configure e-invoice, composition, and filing controls",
    request_model=ComplianceSettingsRequest,
    response_model=ComplianceSettingsResponse,
)
def update_settings() -> tuple[Response, int]:
    body = parse_body(ComplianceSettingsRequest)
    with Session(db.engine) as session:
        company = InvoiceComplianceService(session, g.company_id).configure(
            ComplianceSettingsCommand(
                company_id=g.company_id, user_id=g.user_id, **body.model_dump()
            )
        )
        return model_response(ComplianceSettingsResponse.model_validate(company))


@compliance_bp.get("/invoice-templates")
@require_permission("einvoice.view")
@documented(summary="List Rule 46 invoice templates", response_model=InvoiceTemplateListResponse)
def list_templates() -> tuple[Response, int]:
    with Session(db.engine) as session:
        templates = InvoiceComplianceService(session, g.company_id).templates()
        return model_response(
            InvoiceTemplateListResponse(
                items=[InvoiceTemplateResponse.model_validate(row) for row in templates]
            )
        )


@compliance_bp.post("/invoice-templates")
@require_permission("settings.manage")
@idempotent
@documented(
    summary="Create a Rule 46 validation template",
    request_model=InvoiceTemplateRequest,
    response_model=InvoiceTemplateResponse,
    success_status=201,
)
def create_template() -> tuple[Response, int]:
    body = parse_body(InvoiceTemplateRequest)
    with Session(db.engine) as session:
        template = InvoiceComplianceService(session, g.company_id).create_template(
            InvoiceTemplateCommand(
                company_id=g.company_id,
                user_id=g.user_id,
                mandatory_fields=tuple(body.mandatory_fields),
                **body.model_dump(exclude={"mandatory_fields"}),
            )
        )
        return model_response(InvoiceTemplateResponse.model_validate(template), status=201)
