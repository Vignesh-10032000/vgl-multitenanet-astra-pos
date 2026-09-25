"""Phase 9 e-invoice, e-way bill, and invoice-control API contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from vglpos.api.v1.schemas.common import RequestModel, ResponseModel


class EInvoiceQuery(RequestModel):
    status: str | None = Field(default=None, min_length=1, max_length=20)
    limit: int = Field(default=100, ge=1, le=200)


class EInvoiceResponse(ResponseModel):
    id: int
    sale_id: int
    provider: str
    schema_version: str
    status: str
    irn: str | None
    ack_number: str | None
    ack_date: datetime | None
    error_code: str | None
    error_text: str | None
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    generated_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class EInvoiceListResponse(ResponseModel):
    items: list[EInvoiceResponse]


class EInvoiceCancelRequest(RequestModel):
    reason: str = Field(min_length=1, max_length=100)


class EmptyCommandRequest(RequestModel):
    """Require an explicit empty JSON body for idempotent command endpoints."""


class EWayBillRequest(RequestModel):
    distance_km: int = Field(ge=1, le=4000)
    transporter_id: str | None = Field(default=None, min_length=15, max_length=15)
    transporter_name: str | None = Field(default=None, max_length=100)
    transport_mode: Literal["1", "2", "3", "4"] = "1"
    transport_document_number: str | None = Field(default=None, max_length=15)
    transport_document_date: date | None = None
    vehicle_number: str | None = Field(default=None, min_length=7, max_length=20)
    vehicle_type: Literal["R", "O"] | None = None


class EWayBillResponse(ResponseModel):
    id: int
    sale_id: int
    provider: str
    status: str
    distance_km: int
    transporter_id: str | None
    transporter_name: str | None
    transport_mode: str
    vehicle_number: str | None
    eway_bill_number: str | None
    eway_bill_date: datetime | None
    valid_until: datetime | None
    error_code: str | None
    error_text: str | None
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    created_at: datetime


class EWayBillListResponse(ResponseModel):
    items: list[EWayBillResponse]


class ComplianceAlertResponse(ResponseModel):
    pending_count: int
    dead_letter_count: int
    oldest_pending_at: datetime | None
    exceeds_queue_limit: bool
    exceeds_reporting_window: bool
    active: bool


class ReconciliationIssueResponse(ResponseModel):
    sale_id: int
    invoice_number: str
    business_date: date
    issue: str
    status: str | None
    error_text: str | None


class ReconciliationResponse(ResponseModel):
    items: list[ReconciliationIssueResponse]


class ComplianceSettingsRequest(RequestModel):
    e_invoice_enabled: bool
    e_invoice_provider: Literal["NIC"] = "NIC"
    e_invoice_reporting_window_days: int = Field(ge=1, le=365)
    e_invoice_retry_limit: int = Field(ge=1, le=20)
    composition_scheme_enabled: bool
    composition_declaration: str = Field(min_length=1, max_length=500)
    invoice_validation_enabled: bool
    gst_filing_locked_through: date | None = None


class ComplianceSettingsResponse(ResponseModel):
    e_invoice_enabled: bool
    e_invoice_provider: Literal["NIC"]
    e_invoice_reporting_window_days: int
    e_invoice_retry_limit: int
    composition_scheme_enabled: bool
    composition_declaration: str
    invoice_validation_enabled: bool
    gst_filing_locked_through: date | None


class InvoiceTemplateRequest(RequestModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    paper_size: Literal["58", "80", "A5"] = "A5"
    mandatory_fields: list[str] = Field(min_length=1, max_length=32)
    declaration_text: str | None = Field(default=None, max_length=1000)
    is_default: bool = False


class InvoiceTemplateResponse(ResponseModel):
    id: int
    code: str
    name: str
    paper_size: str
    mandatory_fields: list[str]
    declaration_text: str | None
    is_default: bool
    is_active: bool
    created_at: datetime


class InvoiceTemplateListResponse(ResponseModel):
    items: list[InvoiceTemplateResponse]
