"""Phase 8 batch, expiry, count, variant, and transfer integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.enums import DocType
from vglpos.domain.models import (
    AuditLog,
    Branch,
    CreditNoteItemBatch,
    DocumentSeries,
    SaleItem,
    SaleItemBatch,
    StockBatch,
    StockLedger,
    StockTransferItem,
)
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import InsufficientStockError
from vglpos.services.inventory_depth_service import (
    CreateTransferCommand,
    InventoryDepthService,
    StockCountLineCommand,
    TransferLineCommand,
    VariantCommand,
)
from vglpos.services.inventory_service import InventoryService
from vglpos.services.return_service import (
    CreateCreditNoteCommand,
    ReturnLineCommand,
    ReturnService,
)

from .conftest import ServiceContext, open_service_shift


def _batch(
    session: Session,
    context: ServiceContext,
    *,
    number: str,
    expiry: date,
    quantity: str,
    cost: str,
) -> StockBatch:
    batch = StockBatch(
        company_id=context.company.id,
        branch_id=context.branch.id,
        product_id=context.product.id,
        batch_number=number,
        expiry_date=expiry,
        cost_price=Decimal(cost),
        selling_price=context.product.selling_price,
        quantity_received=Decimal(quantity),
        quantity_available=Decimal(quantity),
        created_by=context.cashier.id,
    )
    session.add(batch)
    session.flush()
    return batch


def test_checkout_allocates_batches_by_fefo_and_snapshots_weighted_cost(
    service_session: Session, service_context: ServiceContext
) -> None:
    service_context.product.batch_tracking_enabled = True
    service_context.product.on_hand = Decimal("5.000")
    first = _batch(
        service_session,
        service_context,
        number="EARLY",
        expiry=date(2026, 10, 1),
        quantity="2.000",
        cost="50.00",
    )
    second = _batch(
        service_session,
        service_context,
        number="LATE",
        expiry=date(2026, 12, 1),
        quantity="3.000",
        cost="70.00",
    )
    service_session.commit()
    open_service_shift(service_session, service_context)

    sale = CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            business_date=date(2026, 9, 23),
            lines=[CheckoutLineCommand(service_context.product.id, "3")],
            payments=[PaymentCommand("CASH", "400.00")],
        )
    )
    sale_item = service_session.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id))
    assert sale_item is not None
    allocations = tuple(
        service_session.scalars(
            select(SaleItemBatch)
            .where(SaleItemBatch.sale_item_id == sale_item.id)
            .order_by(SaleItemBatch.id)
        )
    )
    service_session.refresh(first)
    service_session.refresh(second)

    assert [(row.batch_id, row.quantity) for row in allocations] == [
        (first.id, Decimal("2.000")),
        (second.id, Decimal("1.000")),
    ]
    assert sale_item.cost_at_sale == Decimal("56.67")
    assert first.quantity_available == Decimal("0.000")
    assert second.quantity_available == Decimal("2.000")


def test_expired_batch_policy_blocks_or_warns_and_near_expiry_is_visible(
    service_session: Session, service_context: ServiceContext
) -> None:
    service_context.product.batch_tracking_enabled = True
    service_context.product.on_hand = Decimal("1.000")
    expired = _batch(
        service_session,
        service_context,
        number="EXPIRED",
        expiry=date(2026, 9, 1),
        quantity="1.000",
        cost="40.00",
    )
    service_session.commit()
    open_service_shift(service_session, service_context)
    command = CheckoutCommand(
        company_id=service_context.company.id,
        branch_id=service_context.branch.id,
        terminal_id=service_context.terminal.id,
        cashier_id=service_context.cashier.id,
        business_date=date(2026, 9, 23),
        lines=[CheckoutLineCommand(service_context.product.id, "1")],
        payments=[PaymentCommand("CASH", "120.00")],
    )

    with pytest.raises(InsufficientStockError, match="Eligible batch"):
        CheckoutService(service_session).checkout(command)

    service_context.company.expired_stock_policy = "WARN"
    service_session.commit()
    sale = CheckoutService(service_session).checkout(command)
    warning = service_session.scalar(
        select(AuditLog).where(
            AuditLog.company_id == service_context.company.id,
            AuditLog.action == "EXPIRED_STOCK_WARN",
        )
    )
    rows = InventoryDepthService(service_session, service_context.company.id).near_expiry(
        branch_id=service_context.branch.id,
        on_date=date(2026, 9, 23),
    )

    assert sale.id is not None
    assert warning is not None and warning.entity_id == str(expired.id)
    assert rows == ()  # the sold-out expired batch no longer appears as actionable stock


def test_variant_inherits_hsn_tax_and_keeps_distinct_sku(
    service_session: Session, service_context: ServiceContext
) -> None:
    variant = InventoryDepthService(service_session, service_context.company.id).create_variant(
        VariantCommand(
            company_id=service_context.company.id,
            parent_product_id=service_context.product.id,
            sku="SKU-001-RED-M",
            name="Test Product Red Medium",
            barcode="8900000000999",
            size="M",
            colour="Red",
            style="Regular",
            selling_price="105.00",
            mrp="120.00",
            user_id=service_context.cashier.id,
        )
    )

    assert variant.parent_product_id == service_context.product.id
    assert variant.tax_rate_id == service_context.product.tax_rate_id
    assert variant.hsn_id == service_context.product.hsn_id
    assert variant.sku != service_context.product.sku


def test_physical_count_posts_reasoned_ledger_adjustment(
    service_session: Session, service_context: ServiceContext
) -> None:
    inventory = InventoryService(service_session, service_context.company.id)
    inventory.record_movement(
        service_context.product,
        service_context.branch.id,
        "10",
        "OPENING",
        "opening_stock",
        "PHASE8",
        service_context.cashier.id,
    )
    service_session.commit()
    depth = InventoryDepthService(service_session, service_context.company.id)
    audit = depth.generate_count_sheet(
        branch_id=service_context.branch.id,
        user_id=service_context.cashier.id,
        product_ids=[service_context.product.id],
    )
    from vglpos.domain.models import StockAuditItem

    item = service_session.scalar(
        select(StockAuditItem).where(StockAuditItem.stock_audit_id == audit.id)
    )
    assert item is not None and item.expected_quantity == Decimal("10.000")
    depth.enter_counts(
        stock_audit_id=audit.id,
        user_id=service_context.cashier.id,
        lines=[StockCountLineCommand(item.id, "8", "Two damaged units")],
    )

    posted = depth.post_count(stock_audit_id=audit.id, user_id=service_context.cashier.id)
    adjustment = service_session.scalar(
        select(StockLedger).where(
            StockLedger.reference_type == "stock_audits",
            StockLedger.reference_id == str(audit.id),
        )
    )

    assert posted.status == "POSTED"
    assert adjustment is not None
    assert adjustment.quantity == Decimal("-2.000")
    assert adjustment.notes == "Two damaged units"


def test_branch_transfer_stays_in_transit_until_destination_receipt(
    service_session: Session, service_context: ServiceContext
) -> None:
    destination = Branch(
        company_id=service_context.company.id,
        code="SECOND",
        name="Second Branch",
        state_code="33",
        address_line1="2 Test Street",
        city="Chennai",
        state="Tamil Nadu",
        postal_code="600002",
        phone="8000000002",
    )
    service_session.add(destination)
    service_session.flush()
    service_session.add(
        DocumentSeries(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            doc_type=DocType.STOCK_TRANSFER.value,
            prefix="TR/",
            current_number=0,
            financial_year="26-27",
        )
    )
    InventoryService(service_session, service_context.company.id).record_movement(
        service_context.product,
        service_context.branch.id,
        "5",
        "OPENING",
        "opening_stock",
        "TRANSFER",
        service_context.cashier.id,
    )
    service_session.commit()
    depth = InventoryDepthService(service_session, service_context.company.id)
    transfer = depth.create_transfer(
        CreateTransferCommand(
            company_id=service_context.company.id,
            source_branch_id=service_context.branch.id,
            destination_branch_id=destination.id,
            terminal_id=service_context.terminal.id,
            user_id=service_context.cashier.id,
            transfer_date=date(2026, 9, 23),
            lines=[TransferLineCommand(service_context.product.id, "3")],
        )
    )

    dispatched = depth.dispatch_transfer(
        transfer_id=transfer.id, user_id=service_context.cashier.id
    )
    assert dispatched.status == "IN_TRANSIT"
    assert service_session.scalar(
        select(StockLedger.quantity).where(
            StockLedger.reference_type == "stock_transfers",
            StockLedger.reference_id == str(transfer.id),
            StockLedger.branch_id == service_context.branch.id,
        )
    ) == Decimal("-3.000")

    received = depth.receive_transfer(transfer_id=transfer.id, user_id=service_context.cashier.id)
    transfer_item = service_session.scalar(
        select(StockTransferItem).where(StockTransferItem.stock_transfer_id == transfer.id)
    )
    assert received.status == "RECEIVED"
    assert transfer_item is not None and transfer_item.received_quantity == Decimal("3.000")
    assert service_session.scalar(
        select(StockLedger.quantity).where(
            StockLedger.reference_type == "stock_transfers",
            StockLedger.reference_id == str(transfer.id),
            StockLedger.branch_id == destination.id,
        )
    ) == Decimal("3.000")


def test_return_restores_quantities_to_the_original_sale_batches(
    service_session: Session, service_context: ServiceContext
) -> None:
    service_context.product.batch_tracking_enabled = True
    service_context.product.on_hand = Decimal("3.000")
    first = _batch(
        service_session,
        service_context,
        number="RETURN-EARLY",
        expiry=date(2026, 10, 1),
        quantity="2.000",
        cost="50.00",
    )
    second = _batch(
        service_session,
        service_context,
        number="RETURN-LATE",
        expiry=date(2026, 12, 1),
        quantity="1.000",
        cost="70.00",
    )
    service_session.commit()
    open_service_shift(service_session, service_context)
    sale = CheckoutService(service_session).checkout(
        CheckoutCommand(
            company_id=service_context.company.id,
            branch_id=service_context.branch.id,
            terminal_id=service_context.terminal.id,
            cashier_id=service_context.cashier.id,
            business_date=date(2026, 9, 23),
            lines=[CheckoutLineCommand(service_context.product.id, "3")],
            payments=[PaymentCommand("CASH", "400.00")],
        )
    )
    sale_item = service_session.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id))
    assert sale_item is not None

    ReturnService(service_session).create_credit_note(
        CreateCreditNoteCommand(
            company_id=service_context.company.id,
            original_sale_id=sale.id,
            user_id=service_context.cashier.id,
            reason="CUSTOMER_REQUEST",
            on_date=date(2026, 9, 24),
            lines=[ReturnLineCommand(sale_item.id, "2.500")],
        )
    )
    service_session.refresh(first)
    service_session.refresh(second)
    restored = tuple(
        service_session.scalars(
            select(CreditNoteItemBatch)
            .where(CreditNoteItemBatch.company_id == service_context.company.id)
            .order_by(CreditNoteItemBatch.id)
        )
    )

    assert first.quantity_available == Decimal("2.000")
    assert second.quantity_available == Decimal("0.500")
    assert [(row.batch_id, row.quantity, row.unit_cost) for row in restored] == [
        (first.id, Decimal("2.000"), Decimal("50.00")),
        (second.id, Decimal("0.500"), Decimal("70.00")),
    ]
