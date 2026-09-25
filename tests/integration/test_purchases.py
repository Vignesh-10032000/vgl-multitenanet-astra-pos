"""Phase 8 supplier purchasing and three-way matching integration tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.enums import DocType
from vglpos.domain.models import (
    DocumentSeries,
    GoodsReceiptItem,
    PurchaseItem,
    PurchaseOrderItem,
    StockBatch,
    StockLedger,
    Supplier,
    SupplierLedger,
)
from vglpos.services.exceptions import ConflictError
from vglpos.services.purchase_service import (
    CreateGoodsReceiptCommand,
    CreatePurchaseOrderCommand,
    GoodsReceiptLineCommand,
    PostPurchaseInvoiceCommand,
    PurchaseInvoiceLineCommand,
    PurchaseOrderLineCommand,
    PurchaseReturnCommand,
    PurchaseReturnLineCommand,
    PurchaseService,
    SupplierCommand,
    SupplierPaymentCommand,
)

from .conftest import ServiceContext


def _seed_purchase_configuration(session: Session, context: ServiceContext) -> Supplier:
    context.company.purchase_quantity_tolerance_percent = Decimal("5.00")
    context.company.purchase_price_tolerance_percent = Decimal("5.00")
    context.product.batch_tracking_enabled = True
    context.product.unit_weight_kg = Decimal("0.500")
    for doc_type, prefix in (
        (DocType.PURCHASE_ORDER.value, "PO/"),
        (DocType.GOODS_RECEIPT.value, "GR/"),
        (DocType.DEBIT_NOTE.value, "DN/"),
    ):
        session.add(
            DocumentSeries(
                company_id=context.company.id,
                branch_id=context.branch.id,
                doc_type=doc_type,
                prefix=prefix,
                current_number=0,
                financial_year="26-27",
            )
        )
    session.commit()
    return PurchaseService(session, context.company.id).create_supplier(
        SupplierCommand(
            company_id=context.company.id,
            code="SUP-001",
            name="Test Supplier",
            phone="9000000001",
            state_code="33",
            payment_terms_days=30,
            gstin="33ABCDE1234F1Z5",
            user_id=context.cashier.id,
        )
    )


def test_purchase_order_grn_invoice_updates_stock_cost_and_supplier_ledger(
    service_session: Session, service_context: ServiceContext
) -> None:
    supplier = _seed_purchase_configuration(service_session, service_context)
    service = PurchaseService(service_session, service_context.company.id)
    purchase_order = service.create_purchase_order(
        CreatePurchaseOrderCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            supplier_id=supplier.id,
            user_id=service_context.cashier.id,
            order_date=date(2026, 9, 23),
            lines=[
                PurchaseOrderLineCommand(
                    product_id=service_context.product.id,
                    quantity="10",
                    unit_cost="70.00",
                    tax_rate="18.00",
                )
            ],
        )
    )
    order_item = service_session.scalar(
        select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == purchase_order.id)
    )
    assert order_item is not None
    receipt = service.receive_goods(
        CreateGoodsReceiptCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            purchase_order_id=purchase_order.id,
            user_id=service_context.cashier.id,
            received_at=datetime(2026, 9, 23, 10, tzinfo=UTC),
            lines=[
                GoodsReceiptLineCommand(
                    purchase_order_item_id=order_item.id,
                    quantity="10",
                    unit_cost="70.00",
                    batch_number="B-260923",
                    mfg_date=date(2026, 9, 1),
                    expiry_date=date(2027, 3, 1),
                )
            ],
        )
    )
    receipt_item = service_session.scalar(
        select(GoodsReceiptItem).where(GoodsReceiptItem.goods_receipt_id == receipt.id)
    )
    assert receipt_item is not None
    invoice_command = PostPurchaseInvoiceCommand(
        company_id=service_context.company.id,
        branch_id=service_context.branch.id,
        goods_receipt_id=receipt.id,
        supplier_invoice_number="SUP/INV/1",
        invoice_date=date(2026, 9, 23),
        user_id=service_context.cashier.id,
        landed_cost="100.00",
        landed_cost_method="VALUE",
        lines=[
            PurchaseInvoiceLineCommand(
                goods_receipt_item_id=receipt_item.id,
                billed_quantity="10",
                unit_cost="70.00",
            )
        ],
    )

    preview = service.preview_invoice(invoice_command)

    assert preview.lines[0].old_average_cost == Decimal("60.00")
    assert preview.lines[0].unit_landed_cost == Decimal("80.00")
    assert preview.lines[0].new_average_cost == Decimal("60.20")
    assert preview.total_amount == Decimal("926.00")

    purchase = service.post_invoice(invoice_command)
    service_session.refresh(service_context.product)
    service_session.refresh(supplier)
    batch = service_session.scalar(
        select(StockBatch).where(StockBatch.product_id == service_context.product.id)
    )
    purchase_item = service_session.scalar(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
    )

    assert service_context.product.on_hand == Decimal("1010.000")
    assert service_context.product.cost_price == Decimal("60.20")
    assert batch is not None and batch.quantity_available == Decimal("10.000")
    assert purchase_item is not None and purchase_item.unit_landed_cost == Decimal("80.00")
    assert supplier.outstanding_balance == Decimal("926.00")
    assert (
        service_session.scalar(
            select(StockLedger).where(
                StockLedger.reference_type == "purchases",
                StockLedger.reference_id == str(purchase.id),
            )
        )
        is not None
    )

    debit_note = service.create_purchase_return(
        PurchaseReturnCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            purchase_id=purchase.id,
            user_id=service_context.cashier.id,
            return_date=date(2026, 9, 24),
            reason="Damaged cartons",
            lines=[PurchaseReturnLineCommand(purchase_item.id, "2")],
        )
    )
    service_session.refresh(batch)
    service_session.refresh(supplier)
    assert debit_note.total_amount == Decimal("165.20")
    assert batch.quantity_available == Decimal("8.000")
    assert supplier.outstanding_balance == Decimal("760.80")

    payment = service.record_supplier_payment(
        SupplierPaymentCommand(
            company_id=service_context.company.id,
            supplier_id=supplier.id,
            user_id=service_context.cashier.id,
            payment_date=date(2026, 9, 25),
            amount="60.80",
            reference="BANK-1",
        )
    )
    assert payment.balance_after == Decimal("700.00")
    assert tuple(
        service_session.scalars(
            select(SupplierLedger).where(SupplierLedger.supplier_id == supplier.id)
        )
    )[-1].balance_after == Decimal("700.00")


def test_goods_receipt_rejects_quantity_outside_configured_tolerance(
    service_session: Session, service_context: ServiceContext
) -> None:
    supplier = _seed_purchase_configuration(service_session, service_context)
    service = PurchaseService(service_session, service_context.company.id)
    purchase_order = service.create_purchase_order(
        CreatePurchaseOrderCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            supplier_id=supplier.id,
            user_id=service_context.cashier.id,
            order_date=date(2026, 9, 23),
            lines=[PurchaseOrderLineCommand(service_context.product.id, "10", "70.00", "18.00")],
        )
    )
    order_item = service_session.scalar(
        select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == purchase_order.id)
    )
    assert order_item is not None

    with pytest.raises(ConflictError, match="quantity"):
        service.receive_goods(
            CreateGoodsReceiptCommand(
                company_id=service_context.company.id,
                branch_id=service_context.branch.id,
                terminal_id=service_context.terminal.id,
                purchase_order_id=purchase_order.id,
                user_id=service_context.cashier.id,
                received_at=datetime(2026, 9, 23, 10, tzinfo=UTC),
                lines=[GoodsReceiptLineCommand(order_item.id, "10.501", "70.00")],
            )
        )
