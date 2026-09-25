"""Phase 9 e-invoice, IRP resilience, e-way bill, and compliance tests."""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy.orm import Session

from vglpos.api.v1.serializers import sale_detail_response
from vglpos.domain.events import SaleCompleted
from vglpos.domain.models import EInvoice, HsnCode, Sale
from vglpos.services import event_dispatcher
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.einvoice_service import (
    EInvoiceMapper,
    EInvoiceService,
    EWayBillCommand,
    EWayBillService,
)
from vglpos.services.exceptions import ConflictError, ValidationError
from vglpos.services.invoice_compliance_service import InvoiceComplianceService
from vglpos.services.irp_client import (
    HttpResponse,
    IRPCancelResult,
    IRPEWayBillResult,
    IRPInvoiceResult,
    IRPPermanentError,
    IRPTransientError,
    NICConfig,
    NICIRPClient,
)
from vglpos.services.receipt_delivery import render_a5_invoice_pdf
from vglpos.services.sales_service import SalesService

from .conftest import ServiceContext, open_service_shift


class SuccessfulIRPClient:
    """Deterministic provider double covering all provider-neutral operations."""

    def generate_invoice(self, payload_json: str) -> IRPInvoiceResult:
        assert json.loads(payload_json)["Version"] == "1.1"
        return IRPInvoiceResult(
            irn="1" * 64,
            ack_number="182610000000001",
            ack_date=datetime.now(UTC),
            signed_invoice="signed-invoice",
            signed_qr_code="signed-qr-payload",
            raw_json='{"Status":1}',
        )

    def cancel_invoice(self, *, gstin: str, irn: str, reason: str) -> IRPCancelResult:
        assert gstin.startswith("33")
        assert irn == "1" * 64
        assert reason == "Customer order cancelled"
        return IRPCancelResult(datetime.now(UTC), '{"Status":1}')

    def generate_eway_bill(self, payload_json: str) -> IRPEWayBillResult:
        assert json.loads(payload_json)["vehicleNo"] == "TN01AB1234"
        generated = datetime.now(UTC)
        return IRPEWayBillResult(
            number="181000000001",
            generated_at=generated,
            valid_until=generated + timedelta(days=1),
            raw_json='{"Status":1}',
        )


class UnavailableIRPClient(SuccessfulIRPClient):
    """Provider double for timeout and server-unavailable retry paths."""

    def generate_invoice(self, payload_json: str) -> IRPInvoiceResult:
        raise IRPTransientError("IRP is unreachable.", code="TIMEOUT")


class SchemaRejectingIRPClient(SuccessfulIRPClient):
    """Provider double for a permanent remote schema rejection."""

    def generate_invoice(self, payload_json: str) -> IRPInvoiceResult:
        raise IRPPermanentError("IRP schema validation failed.", code="SCHEMA_INVALID")


class MemoryTokenStore:
    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self.set_values: list[tuple[str, int]] = []
        self.delete_count = 0

    def get(self, key: str) -> str | None:
        return self.token

    def set(self, key: str, value: str, timeout: int) -> None:
        self.token = value
        self.set_values.append((value, timeout))

    def delete(self, key: str) -> None:
        self.token = None
        self.delete_count += 1


class QueuedTransport:
    def __init__(self, *responses: HttpResponse | Exception) -> None:
        self.responses = deque(responses)
        self.headers: list[dict[str, str]] = []
        self.urls: list[str] = []

    def post(self, url: str, *, headers: dict[str, str], body: bytes) -> HttpResponse:
        self.urls.append(url)
        self.headers.append(headers)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def _nic_config() -> NICConfig:
    return NICConfig(
        auth_url="https://sandbox.invalid/auth",
        generate_url="https://sandbox.invalid/generate",
        lookup_url="https://sandbox.invalid/lookup",
        cancel_url="https://sandbox.invalid/cancel",
        eway_url="https://sandbox.invalid/eway",
        username="configured-user",
        password="configured-password",
        client_id="configured-client",
        client_secret="configured-secret",
    )


def _configure_invoice_facts(
    session: Session,
    context: ServiceContext,
    *,
    with_hsn: bool = True,
    composition: bool = False,
) -> None:
    context.company.gstin = "33AACCR7832C1ZO"
    context.company.e_invoice_enabled = True
    context.company.composition_scheme_enabled = composition
    context.branch.gstin = "33AACCR7832C1ZO"
    context.customer.gstin = "29AACCR7832C1ZD"
    context.customer.state_code = "29"
    context.customer.address = "1 Buyer Road"
    context.customer.city = "Bengaluru"
    context.customer.postal_code = "560001"
    if with_hsn:
        hsn = HsnCode(
            code="1001",
            description="Test goods",
            default_tax_rate_id=context.tax_rate.id,
        )
        session.add(hsn)
        session.flush()
        context.product.hsn_id = hsn.id
    session.commit()


def _checkout_sale(
    session: Session,
    context: ServiceContext,
    *,
    with_hsn: bool = True,
    composition: bool = False,
) -> Sale:
    _configure_invoice_facts(
        session,
        context,
        with_hsn=with_hsn,
        composition=composition,
    )
    open_service_shift(session, context)
    payment = "100.00" if composition else "118.00"
    return CheckoutService(session).checkout(
        CheckoutCommand(
            company_id=context.company.id,
            branch_id=context.branch.id,
            terminal_id=context.terminal.id,
            cashier_id=context.cashier.id,
            customer_id=context.customer.id,
            business_date=datetime.now(UTC).date(),
            lines=[CheckoutLineCommand(context.product.id, "1")],
            payments=[PaymentCommand("CASH", payment)],
        )
    )


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def test_mapper_and_successful_lifecycle_preserve_decimal_tax_facts(
    service_session: Session, service_context: ServiceContext
) -> None:
    sale = _checkout_sale(service_session, service_context)
    service = EInvoiceService(service_session, service_context.company.id)

    payload_json = EInvoiceMapper(service_session, service_context.company.id).invoice_json(sale.id)
    payload = json.loads(payload_json, parse_float=Decimal)
    assert payload["Version"] == "1.1"
    assert payload["SellerDtls"]["Gstin"] == "33AACCR7832C1ZO"
    assert payload["BuyerDtls"]["Gstin"] == "29AACCR7832C1ZD"
    assert payload["ItemList"][0]["HsnCd"] == "1001"
    assert payload["ValDtls"]["IgstVal"] == Decimal("18.00")
    assert payload["ValDtls"]["TotInvVal"] == Decimal("118.00")
    assert not _contains_float(payload)

    assert service.reconciliation()[0].issue == "MISSING"
    record = service.queue_sale(sale.id)
    assert record is not None and record.status == "PENDING"
    assert service.queue_sale(sale.id).id == record.id  # type: ignore[union-attr]

    generated = service.process(record.id, SuccessfulIRPClient())
    assert generated.status == "GENERATED"
    assert generated.irn == "1" * 64
    assert generated.signed_qr_code == "signed-qr-payload"
    assert service.reconciliation() == ()
    detail = SalesService(service_session, service_context.company.id).sale_detail(sale.id)
    response = sale_detail_response(detail)
    assert response.e_invoice is not None
    assert response.e_invoice.qr_data_uri is not None
    assert response.e_invoice.qr_data_uri.startswith("data:image/png;base64,")
    pdf = render_a5_invoice_pdf(detail)
    assert pdf.startswith(b"%PDF-1.4")
    assert b"IRN: " + (b"1" * 64) in pdf
    assert b" re f" in pdf

    pending_cancel = service.request_cancellation(
        generated.id,
        user_id=service_context.cashier.id,
        reason="Customer order cancelled",
    )
    assert pending_cancel.status == "CANCEL_PENDING"
    cancelled = service.process(record.id, SuccessfulIRPClient())
    assert cancelled.status == "CANCELLED"
    assert cancelled.cancelled_at is not None


def test_sale_remains_completed_while_unreachable_irp_retries_then_dead_letters(
    service_session: Session, service_context: ServiceContext
) -> None:
    sale = _checkout_sale(service_session, service_context)
    service_context.company.e_invoice_retry_limit = 2
    service_session.commit()
    service = EInvoiceService(service_session, service_context.company.id)
    record = service.queue_sale(sale.id)
    assert record is not None

    record.status = "PROCESSING"
    record.last_attempt_at = datetime.now(UTC) - timedelta(minutes=10)
    service_session.commit()
    recovered = service.recover_stale_processing(now=datetime.now(UTC))
    assert [item.id for item in recovered] == [record.id]
    assert recovered[0].status == "RETRY"
    assert recovered[0].error_code == "WORKER_INTERRUPTED"

    first = service.process(record.id, UnavailableIRPClient())
    assert first.status == "RETRY"
    assert first.next_attempt_at is not None
    second = service.process(record.id, UnavailableIRPClient())
    assert second.status == "DEAD"
    assert second.error_code == "TIMEOUT"
    assert service_session.get(Sale, sale.id).sale_status == "COMPLETED"  # type: ignore[union-attr]


def test_tax_inclusive_sale_maps_to_tax_exclusive_irp_item_values(
    service_session: Session, service_context: ServiceContext
) -> None:
    service_context.product.is_tax_inclusive = True
    service_context.product.selling_price = Decimal("118.00")
    service_session.commit()
    sale = _checkout_sale(service_session, service_context)

    payload = json.loads(
        EInvoiceMapper(service_session, service_context.company.id).invoice_json(sale.id),
        parse_float=Decimal,
    )
    item = payload["ItemList"][0]

    assert item["UnitPrice"] == Decimal("100.00")
    assert item["TotAmt"] == Decimal("100.00")
    assert item["AssAmt"] == Decimal("100.00")
    assert item["IgstAmt"] == Decimal("18.00")
    assert item["TotItemVal"] == Decimal("118.00")


def test_local_schema_rejection_is_durable_and_never_calls_irp(
    service_session: Session, service_context: ServiceContext
) -> None:
    sale = _checkout_sale(service_session, service_context, with_hsn=False)
    record = EInvoiceService(service_session, service_context.company.id).queue_sale(sale.id)

    assert record is not None
    assert record.status == "DEAD"
    assert record.error_code == "LOCAL_SCHEMA"
    assert "HSN" in (record.error_text or "")
    with pytest.raises(ValidationError, match="still invalid"):
        EInvoiceService(service_session, service_context.company.id).retry(
            record.id, user_id=service_context.cashier.id
        )


def test_remote_schema_rejection_keeps_sale_and_supports_reviewed_retry(
    service_session: Session, service_context: ServiceContext
) -> None:
    sale = _checkout_sale(service_session, service_context)
    service = EInvoiceService(service_session, service_context.company.id)
    record = service.queue_sale(sale.id)
    assert record is not None

    rejected = service.process(record.id, SchemaRejectingIRPClient())
    assert rejected.status == "DEAD"
    assert rejected.error_code == "SCHEMA_INVALID"
    assert service_session.get(Sale, sale.id).sale_status == "COMPLETED"  # type: ignore[union-attr]

    retried = service.retry(record.id, user_id=service_context.cashier.id)
    assert retried.status == "PENDING"
    assert retried.attempt_count == 0
    assert retried.error_text is None


def test_e_way_bill_uses_urp_for_unregistered_buyer_and_shared_retry_state(
    service_session: Session, service_context: ServiceContext
) -> None:
    sale = _checkout_sale(service_session, service_context)
    service_context.customer.gstin = None
    service_session.commit()
    service = EWayBillService(service_session, service_context.company.id)
    command = EWayBillCommand(
        company_id=service_context.company.id,
        sale_id=sale.id,
        user_id=service_context.cashier.id,
        distance_km=25,
        transport_mode="1",
        vehicle_number="TN01AB1234",
        vehicle_type="R",
    )

    record = service.create(command)
    payload = json.loads(record.request_json, parse_float=Decimal)
    assert payload["toGstin"] == "URP"
    assert service.create(command).id == record.id
    record.status = "PROCESSING"
    record.last_attempt_at = datetime.now(UTC) - timedelta(minutes=10)
    service_session.commit()
    assert service.recover_stale_processing(now=datetime.now(UTC))[0].status == "RETRY"
    generated = service.process(record.id, SuccessfulIRPClient())
    assert generated.status == "GENERATED"
    assert generated.eway_bill_number == "181000000001"


def test_composition_mode_suppresses_tax_and_e_invoice_queue(
    service_session: Session, service_context: ServiceContext
) -> None:
    sale = _checkout_sale(service_session, service_context, composition=True)

    assert sale.net_amount == Decimal("100.00")
    assert sale.cgst_amount == sale.sgst_amount == sale.igst_amount == Decimal("0.00")
    assert EInvoiceService(service_session, service_context.company.id).queue_sale(sale.id) is None
    detail = SalesService(service_session, service_context.company.id).sale_detail(sale.id)
    assert detail.composition_declaration == service_context.company.composition_declaration
    assert detail.composition_declaration.encode() in render_a5_invoice_pdf(detail)


def test_rule46_and_filing_lock_block_invalid_issue_and_cancellation(
    service_session: Session, service_context: ServiceContext
) -> None:
    _configure_invoice_facts(service_session, service_context)
    service_context.company.invoice_validation_enabled = True
    service_context.company.gstin = None
    service_context.branch.gstin = None
    service_session.commit()
    open_service_shift(service_session, service_context)
    command = CheckoutCommand(
        company_id=service_context.company.id,
        branch_id=service_context.branch.id,
        terminal_id=service_context.terminal.id,
        cashier_id=service_context.cashier.id,
        customer_id=service_context.customer.id,
        business_date=datetime.now(UTC).date(),
        lines=[CheckoutLineCommand(service_context.product.id, "1")],
        payments=[PaymentCommand("CASH", "118.00")],
    )
    with pytest.raises(ValidationError, match="supplier_gstin"):
        CheckoutService(service_session).checkout(command)

    service_context.company.invoice_validation_enabled = False
    service_context.company.gstin = "33AACCR7832C1ZO"
    service_context.branch.gstin = "33AACCR7832C1ZO"
    service_session.commit()
    sale = CheckoutService(service_session).checkout(command)
    service_context.company.gst_filing_locked_through = sale.business_date
    service_session.commit()

    with pytest.raises(ConflictError, match="filed GST period"):
        InvoiceComplianceService(
            service_session, service_context.company.id
        ).enforce_sale_cancellation(sale, now=datetime.now(UTC))


def test_queue_alert_detects_volume_dead_letters_and_configurable_age(
    service_session: Session, service_context: ServiceContext
) -> None:
    now = datetime.now(UTC)
    service_context.company.e_invoice_reporting_window_days = 7
    for number in range(52):
        sale = Sale(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            invoice_number=f"ALERT/{number + 1}",
            business_date=now.date(),
            sale_status="COMPLETED",
            supply_type="INTRASTATE",
            gross_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            taxable_amount=Decimal("0.00"),
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00"),
            igst_amount=Decimal("0.00"),
            cess_amount=Decimal("0.00"),
            round_off=Decimal("0.00"),
            net_amount=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
            balance_due=Decimal("0.00"),
            payment_method="CASH",
            created_by=service_context.cashier.id,
        )
        service_session.add(sale)
        service_session.flush()
        service_session.add(
            EInvoice(
                company_id=service_context.company.id,
                sale_id=sale.id,
                provider="NIC",
                status="PENDING" if number < 51 else "DEAD",
                max_attempts=5,
                created_at=now - timedelta(days=8) if number == 0 else now,
                created_by=service_context.cashier.id,
            )
        )
    service_session.commit()

    alert = EInvoiceService(service_session, service_context.company.id).alert(now=now)

    assert alert.pending_count == 51
    assert alert.dead_letter_count == 1
    assert alert.exceeds_queue_limit is True
    assert alert.exceeds_reporting_window is True
    assert alert.active is True


def test_nic_adapter_recovers_duplicate_irn_as_success() -> None:
    duplicate = {
        "Status": 0,
        "ErrorDetails": [{"ErrorCode": "2150", "ErrorMessage": "Duplicate IRN"}],
        "Data": {
            "Irn": "2" * 64,
            "AckNo": "182610000000002",
            "AckDt": "25/09/2026 10:30:00",
            "SignedInvoice": "signed-invoice",
            "SignedQRCode": "signed-qr",
        },
    }
    transport = QueuedTransport(
        HttpResponse(200, json.dumps(duplicate, separators=(",", ":")).encode())
    )
    client = NICIRPClient(
        _nic_config(), transport=transport, token_store=MemoryTokenStore("cached-token")
    )

    result = client.generate_invoice('{"SellerDtls":{"Gstin":"33AACCR7832C1ZO"}}')

    assert result.duplicate is True
    assert result.irn == "2" * 64


def test_nic_adapter_looks_up_duplicate_when_generation_omits_irn() -> None:
    duplicate = {
        "Status": 0,
        "ErrorDetails": [{"ErrorCode": "2150", "ErrorMessage": "Duplicate IRN"}],
    }
    lookup = {
        "Status": 1,
        "Data": {
            "Irn": "4" * 64,
            "AckNo": "182610000000004",
            "AckDt": "25/09/2026 10:30:00",
            "SignedInvoice": "signed-invoice",
            "SignedQRCode": "signed-qr",
        },
    }
    transport = QueuedTransport(
        HttpResponse(200, json.dumps(duplicate).encode()),
        HttpResponse(200, json.dumps(lookup).encode()),
    )
    client = NICIRPClient(
        _nic_config(), transport=transport, token_store=MemoryTokenStore("cached-token")
    )
    payload = {
        "SellerDtls": {"Gstin": "33AACCR7832C1ZO"},
        "DocDtls": {"Typ": "INV", "No": "S/1", "Dt": "25/09/2026"},
    }

    result = client.generate_invoice(json.dumps(payload))

    assert result.duplicate is True
    assert result.irn == "4" * 64
    assert transport.urls == [_nic_config().generate_url, _nic_config().lookup_url]


def test_nic_adapter_refreshes_expired_token_once() -> None:
    token_error = {
        "Status": 0,
        "ErrorDetails": [{"ErrorCode": "1005", "ErrorMessage": "Token expired"}],
    }
    auth = {"Status": 1, "Data": {"AuthToken": "fresh-token", "TokenExpiry": 3600}}
    generated = {
        "Status": 1,
        "Data": {
            "Irn": "3" * 64,
            "AckNo": "182610000000003",
            "AckDt": "2026-09-25T10:30:00+00:00",
            "SignedInvoice": "signed-invoice",
            "SignedQRCode": "signed-qr",
        },
    }
    transport = QueuedTransport(
        HttpResponse(200, json.dumps(token_error).encode()),
        HttpResponse(200, json.dumps(auth).encode()),
        HttpResponse(200, json.dumps(generated).encode()),
    )
    token_store = MemoryTokenStore("expired-token")
    client = NICIRPClient(_nic_config(), transport=transport, token_store=token_store)

    result = client.generate_invoice('{"SellerDtls":{"Gstin":"33AACCR7832C1ZO"}}')

    assert result.irn == "3" * 64
    assert token_store.delete_count == 1
    assert token_store.set_values == [("fresh-token", 3540)]
    assert transport.headers[0]["auth-token"] == "expired-token"
    assert transport.headers[2]["auth-token"] == "fresh-token"


@pytest.mark.parametrize(
    "provider_failure",
    [
        HttpResponse(503, b'{"message":"unavailable"}'),
        IRPTransientError("IRP is unreachable.", code="TIMEOUT"),
    ],
    ids=["http-5xx", "timeout"],
)
def test_nic_adapter_classifies_timeout_and_5xx_as_retryable(
    provider_failure: HttpResponse | Exception,
) -> None:
    client = NICIRPClient(
        _nic_config(),
        transport=QueuedTransport(provider_failure),
        token_store=MemoryTokenStore("cached-token"),
    )

    with pytest.raises(IRPTransientError):
        client.generate_invoice('{"SellerDtls":{"Gstin":"33AACCR7832C1ZO"}}')


def test_broker_outage_during_post_commit_queueing_does_not_escape(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        event_dispatcher.EInvoiceService,
        "queue_sale",
        lambda self, sale_id: SimpleNamespace(id=99, status="PENDING"),
    )

    def unavailable_broker(**kwargs: int) -> None:
        raise OSError("broker unavailable")

    monkeypatch.setattr(event_dispatcher.process_einvoice, "delay", unavailable_broker)

    with app.app_context():
        event_dispatcher.publish_event(
            SaleCompleted(
                company_id=1,
                branch_id=1,
                sale_id=1,
                occurred_at=datetime.now(UTC),
            )
        )


def test_nic_sandbox_generation_and_cancellation() -> None:
    """Run only with explicit credentials and a unique sandbox invoice payload."""
    if os.getenv("RUN_NIC_SANDBOX_TESTS") != "1":
        pytest.skip("Set RUN_NIC_SANDBOX_TESTS=1 for the opt-in NIC sandbox gate.")
    names = (
        "IRP_NIC_AUTH_URL",
        "IRP_NIC_GENERATE_URL",
        "IRP_NIC_LOOKUP_URL",
        "IRP_NIC_CANCEL_URL",
        "IRP_NIC_EWAY_URL",
        "IRP_NIC_USERNAME",
        "IRP_NIC_PASSWORD",
        "IRP_NIC_CLIENT_ID",
        "IRP_NIC_CLIENT_SECRET",
        "NIC_SANDBOX_EINVOICE_PAYLOAD",
    )
    values = {name: os.getenv(name, "").strip() for name in names}
    missing = sorted(name for name, value in values.items() if not value)
    assert not missing, f"NIC sandbox configuration is missing: {', '.join(missing)}"
    payload_path = Path(values["NIC_SANDBOX_EINVOICE_PAYLOAD"])
    payload_json = payload_path.read_text(encoding="utf-8")
    payload = json.loads(payload_json)
    seller_gstin = payload["SellerDtls"]["Gstin"]
    client = NICIRPClient(
        NICConfig(
            auth_url=values["IRP_NIC_AUTH_URL"],
            generate_url=values["IRP_NIC_GENERATE_URL"],
            lookup_url=values["IRP_NIC_LOOKUP_URL"],
            cancel_url=values["IRP_NIC_CANCEL_URL"],
            eway_url=values["IRP_NIC_EWAY_URL"],
            username=values["IRP_NIC_USERNAME"],
            password=values["IRP_NIC_PASSWORD"],
            client_id=values["IRP_NIC_CLIENT_ID"],
            client_secret=values["IRP_NIC_CLIENT_SECRET"],
        ),
        token_store=MemoryTokenStore(),
    )

    result = client.generate_invoice(payload_json)
    assert len(result.irn) == 64
    assert result.ack_number
    assert result.signed_qr_code
    cancelled = client.cancel_invoice(
        gstin=seller_gstin,
        irn=result.irn,
        reason="Automated NIC sandbox integration test",
    )
    assert cancelled.cancelled_at is not None
