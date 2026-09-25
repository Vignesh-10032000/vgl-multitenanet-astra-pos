"""Batch custody, variants, stock counts, transfers, and replenishment workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.enums import DocType, LedgerTxnType
from vglpos.domain.models import (
    Branch,
    Company,
    Product,
    Sale,
    SaleItem,
    SaleItemBatch,
    StockAudit,
    StockAuditItem,
    StockBatch,
    StockLedger,
    StockTransfer,
    StockTransferItem,
)
from vglpos.security.audit import record_audit_event
from vglpos.services.exceptions import (
    ConflictError,
    EntityNotFoundError,
    InsufficientStockError,
    ValidationError,
)
from vglpos.services.inventory_service import InventoryService
from vglpos.services.invoice_number_service import InvoiceNumberService
from vglpos.utils.money import ZERO, money, qty, to_decimal

ZERO_QTY = Decimal("0.000")


@dataclass(frozen=True, slots=True)
class BatchAllocation:
    batch_id: int
    batch_number: str
    expiry_date: date | None
    quantity: Decimal
    unit_cost: Decimal
    expired: bool


@dataclass(frozen=True, slots=True)
class NearExpiryRow:
    batch_id: int
    product_id: int
    batch_number: str
    expiry_date: date
    quantity_available: Decimal
    days_remaining: int
    expired: bool


@dataclass(frozen=True, slots=True)
class VariantCommand:
    company_id: int
    parent_product_id: int
    sku: str
    name: str
    selling_price: object
    mrp: object
    user_id: int
    barcode: str | None = None
    size: str | None = None
    colour: str | None = None
    style: str | None = None


@dataclass(frozen=True, slots=True)
class StockCountLineCommand:
    stock_audit_item_id: int
    counted_quantity: object
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class TransferLineCommand:
    product_id: int
    quantity: object
    source_batch_id: int | None = None


@dataclass(frozen=True, slots=True)
class CreateTransferCommand:
    company_id: int
    source_branch_id: int
    destination_branch_id: int
    terminal_id: int
    user_id: int
    transfer_date: date
    lines: tuple[TransferLineCommand, ...] | list[TransferLineCommand]
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ReorderSuggestion:
    product_id: int
    sku: str
    on_hand: Decimal
    daily_velocity: Decimal
    lead_time_days: int
    safety_stock: Decimal
    suggested_quantity: Decimal


@dataclass(frozen=True, slots=True)
class StockValueRow:
    product_id: int
    sku: str
    quantity: Decimal
    cost_value: Decimal
    retail_value: Decimal


class InventoryDepthService:
    """Coordinate lot-aware workflows while retaining the append-only stock ledger."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def create_variant(self, command: VariantCommand) -> Product:
        """Create a child SKU that inherits statutory facts from its parent."""
        self._require_command_company(command.company_id)
        parent = self._require_product(command.parent_product_id)
        sku = command.sku.strip().upper()
        name = command.name.strip()
        selling_price = self._money(command.selling_price, "Selling price")
        mrp = self._money(command.mrp, "MRP")
        if not sku or not name:
            raise ValidationError("Variant SKU and name are required.")
        if selling_price < ZERO or mrp < selling_price:
            raise ValidationError("Variant MRP must be at least its selling price.")
        if not any((command.size, command.colour, command.style)):
            raise ValidationError("At least one size, colour, or style attribute is required.")
        variant = Product(
            company_id=self.company_id,
            parent_product_id=parent.id,
            preferred_supplier_id=parent.preferred_supplier_id,
            sku=sku,
            name=name,
            brand=parent.brand,
            category_id=parent.category_id,
            hsn_id=parent.hsn_id,
            tax_rate_id=parent.tax_rate_id,
            barcode=command.barcode.strip() if command.barcode else None,
            variant_size=command.size.strip() if command.size else None,
            variant_colour=command.colour.strip() if command.colour else None,
            variant_style=command.style.strip() if command.style else None,
            uom=parent.uom,
            cost_price=parent.cost_price,
            selling_price=selling_price,
            mrp=mrp,
            is_tax_inclusive=parent.is_tax_inclusive,
            is_inventory_tracked=parent.is_inventory_tracked,
            batch_tracking_enabled=parent.batch_tracking_enabled,
            is_weighed=parent.is_weighed,
            low_stock_threshold=parent.low_stock_threshold,
            safety_stock=parent.safety_stock,
            lead_time_days=parent.lead_time_days,
            unit_weight_kg=parent.unit_weight_kg,
            allow_negative_stock=parent.allow_negative_stock,
            created_by=command.user_id,
        )
        self.session.add(variant)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Variant SKU or barcode already exists.") from exc
        self.session.refresh(variant)
        return variant

    def ensure_fefo_availability(
        self,
        *,
        product: Product,
        branch_id: int,
        quantity: object,
        on_date: date,
        expired_policy: str,
    ) -> None:
        """Reject a cart early when eligible FEFO lots cannot satisfy it."""
        required = self._positive_qty(quantity, "Sale quantity")
        batches = self._fefo_batches(
            product=product,
            branch_id=branch_id,
            on_date=on_date,
            expired_policy=expired_policy,
            for_update=False,
        )
        available = qty(sum((batch.quantity_available for batch in batches), ZERO_QTY))
        if available < required:
            raise InsufficientStockError(
                f"Eligible batch stock for product {product.id} is {available}; "
                f"requested {required}."
            )

    def allocate_fefo(
        self,
        *,
        sale_item: SaleItem,
        product: Product,
        branch_id: int,
        quantity: object,
        on_date: date,
        expired_policy: str,
        user_id: int,
    ) -> tuple[BatchAllocation, ...]:
        """Consume earliest-expiring lots and persist the immutable sale allocation."""
        required = self._positive_qty(quantity, "Sale quantity")
        batches = self._fefo_batches(
            product=product,
            branch_id=branch_id,
            on_date=on_date,
            expired_policy=expired_policy,
            for_update=True,
        )
        remaining = required
        allocations: list[BatchAllocation] = []
        inventory = InventoryService(self.session, self.company_id)
        for batch in batches:
            if remaining <= ZERO_QTY:
                break
            consumed = min(qty(batch.quantity_available), remaining)
            if consumed <= ZERO_QTY:
                continue
            batch.quantity_available = qty(batch.quantity_available - consumed)
            batch.row_version += 1
            expired = batch.expiry_date is not None and batch.expiry_date < on_date
            allocation = BatchAllocation(
                batch_id=batch.id,
                batch_number=batch.batch_number,
                expiry_date=batch.expiry_date,
                quantity=consumed,
                unit_cost=money(batch.cost_price),
                expired=expired,
            )
            allocations.append(allocation)
            self.session.add(
                SaleItemBatch(
                    company_id=self.company_id,
                    sale_item_id=sale_item.id,
                    batch_id=batch.id,
                    quantity=consumed,
                    unit_cost=batch.cost_price,
                    created_by=user_id,
                )
            )
            inventory.record_movement(
                product,
                branch_id,
                -consumed,
                LedgerTxnType.SALE.value,
                "sales",
                sale_item.sale_id,
                user_id,
                batch_id=batch.id,
                unit_cost=batch.cost_price,
            )
            if expired:
                record_audit_event(
                    self.session,
                    company_id=self.company_id,
                    user_id=user_id,
                    action="EXPIRED_STOCK_WARN",
                    entity_type="StockBatch",
                    entity_id=batch.id,
                    new_values={"sale_item_id": sale_item.id, "quantity": str(consumed)},
                )
            remaining = qty(remaining - consumed)
        if remaining > ZERO_QTY:
            raise InsufficientStockError(
                f"Eligible batch stock for product {product.id} is insufficient by {remaining}."
            )
        total_cost = money(sum((row.quantity * row.unit_cost for row in allocations), ZERO))
        sale_item.cost_at_sale = money(total_cost / required)
        return tuple(allocations)

    def near_expiry(
        self, *, branch_id: int, on_date: date, days: int | None = None
    ) -> tuple[NearExpiryRow, ...]:
        """Return active lots expiring inside the configured operational window."""
        company = self._require_company()
        window = company.near_expiry_days if days is None else days
        if window < 0 or window > 3650:
            raise ValidationError("Near-expiry window must be between 0 and 3650 days.")
        self._require_branch(branch_id)
        batches = self.session.scalars(
            select(StockBatch)
            .where(
                StockBatch.company_id == self.company_id,
                StockBatch.branch_id == branch_id,
                StockBatch.deleted_at.is_(None),
                StockBatch.is_active.is_(True),
                StockBatch.quantity_available > ZERO_QTY,
                StockBatch.expiry_date.is_not(None),
                StockBatch.expiry_date <= on_date + timedelta(days=window),
            )
            .order_by(StockBatch.expiry_date, StockBatch.id)
        )
        return tuple(
            NearExpiryRow(
                batch_id=batch.id,
                product_id=batch.product_id,
                batch_number=batch.batch_number,
                expiry_date=batch.expiry_date,
                quantity_available=qty(batch.quantity_available),
                days_remaining=(batch.expiry_date - on_date).days,
                expired=batch.expiry_date < on_date,
            )
            for batch in batches
            if batch.expiry_date is not None
        )

    def generate_count_sheet(
        self,
        *,
        branch_id: int,
        user_id: int,
        product_ids: tuple[int, ...] | list[int] | None = None,
    ) -> StockAudit:
        """Freeze expected branch balances into a blind physical-count worksheet."""
        self._require_branch(branch_id)
        statement = select(Product).where(
            Product.company_id == self.company_id,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Product.is_inventory_tracked.is_(True),
        )
        if product_ids:
            statement = statement.where(Product.id.in_(sorted(set(product_ids))))
        products = tuple(self.session.scalars(statement.order_by(Product.id)))
        if not products:
            raise ValidationError("Count sheet requires at least one active inventory product.")
        audit = StockAudit(
            company_id=self.company_id,
            branch_id=branch_id,
            audit_number=f"SA-{datetime.now(UTC):%Y%m%d%H%M%S%f}",
            status="DRAFT",
            created_by=user_id,
        )
        self.session.add(audit)
        self.session.flush()
        for product in products:
            batches = tuple(
                self.session.scalars(
                    select(StockBatch).where(
                        StockBatch.company_id == self.company_id,
                        StockBatch.branch_id == branch_id,
                        StockBatch.product_id == product.id,
                        StockBatch.deleted_at.is_(None),
                        StockBatch.is_active.is_(True),
                    )
                )
            )
            if product.batch_tracking_enabled and batches:
                for batch in batches:
                    self._add_count_line(
                        audit, product.id, batch.id, qty(batch.quantity_available), user_id
                    )
            else:
                self._add_count_line(
                    audit,
                    product.id,
                    None,
                    self._branch_balance(branch_id, product.id),
                    user_id,
                )
        self.session.commit()
        self.session.refresh(audit)
        return audit

    def enter_counts(
        self,
        *,
        stock_audit_id: int,
        user_id: int,
        lines: tuple[StockCountLineCommand, ...] | list[StockCountLineCommand],
    ) -> StockAudit:
        """Record blind counts while preserving expected quantities for review."""
        audit = self._require_audit(stock_audit_id, status="DRAFT", for_update=True)
        items = {
            item.id: item
            for item in self.session.scalars(
                select(StockAuditItem).where(
                    StockAuditItem.company_id == self.company_id,
                    StockAuditItem.stock_audit_id == audit.id,
                    StockAuditItem.deleted_at.is_(None),
                )
            )
        }
        if {line.stock_audit_item_id for line in lines} != items.keys():
            raise ValidationError("Every count-sheet line must be submitted exactly once.")
        for line in lines:
            item = items[line.stock_audit_item_id]
            counted = self._nonnegative_qty(line.counted_quantity, "Counted quantity")
            item.counted_quantity = counted
            item.variance_quantity = qty(counted - item.expected_quantity)
            item.reason = line.reason.strip() if line.reason else None
            if item.variance_quantity != ZERO_QTY and not item.reason:
                raise ValidationError("A reason is required for every stock-count variance.")
            item.updated_by = user_id
        audit.status = "REVIEW"
        audit.counted_at = datetime.now(UTC)
        audit.updated_by = user_id
        self.session.commit()
        self.session.refresh(audit)
        return audit

    def post_count(self, *, stock_audit_id: int, user_id: int) -> StockAudit:
        """Post reviewed variances exclusively through stock and batch ledgers."""
        audit = self._require_audit(stock_audit_id, status="REVIEW", for_update=True)
        items = tuple(
            self.session.scalars(
                select(StockAuditItem).where(
                    StockAuditItem.company_id == self.company_id,
                    StockAuditItem.stock_audit_id == audit.id,
                    StockAuditItem.deleted_at.is_(None),
                )
            )
        )
        products = self._load_products({item.product_id for item in items}, for_update=True)
        inventory = InventoryService(self.session, self.company_id)
        for item in items:
            if item.variance_quantity is None:
                raise ConflictError("Stock audit contains an uncounted line.")
            if item.variance_quantity == ZERO_QTY:
                continue
            if item.batch_id is not None:
                batch = self.session.scalar(
                    select(StockBatch)
                    .where(
                        StockBatch.id == item.batch_id,
                        StockBatch.company_id == self.company_id,
                        StockBatch.branch_id == audit.branch_id,
                        StockBatch.deleted_at.is_(None),
                    )
                    .with_for_update()
                )
                if batch is None or batch.quantity_available + item.variance_quantity < ZERO_QTY:
                    raise ConflictError("Stock audit would make a batch balance negative.")
                batch.quantity_available = qty(batch.quantity_available + item.variance_quantity)
                batch.row_version += 1
            inventory.record_movement(
                products[item.product_id],
                audit.branch_id,
                item.variance_quantity,
                LedgerTxnType.ADJUSTMENT.value,
                "stock_audits",
                audit.id,
                user_id,
                batch_id=item.batch_id,
                notes=item.reason,
            )
        audit.status = "POSTED"
        audit.posted_at = datetime.now(UTC)
        audit.updated_by = user_id
        record_audit_event(
            self.session,
            company_id=self.company_id,
            user_id=user_id,
            action="STOCK_AUDIT_POST",
            entity_type="StockAudit",
            entity_id=audit.id,
        )
        self.session.commit()
        self.session.refresh(audit)
        return audit

    def create_transfer(self, command: CreateTransferCommand) -> StockTransfer:
        """Create a draft inter-branch transfer without changing stock."""
        self._require_command_company(command.company_id)
        if command.source_branch_id == command.destination_branch_id:
            raise ValidationError("Stock transfer branches must be different.")
        self._require_branch(command.source_branch_id)
        self._require_branch(command.destination_branch_id)
        if not command.lines:
            raise ValidationError("Stock transfer requires at least one line.")
        products = self._load_products({line.product_id for line in command.lines})
        number, _ = InvoiceNumberService(self.session).allocate(
            self.company_id,
            command.source_branch_id,
            command.terminal_id,
            DocType.STOCK_TRANSFER.value,
            command.transfer_date,
        )
        transfer = StockTransfer(
            company_id=self.company_id,
            source_branch_id=command.source_branch_id,
            destination_branch_id=command.destination_branch_id,
            transfer_number=number,
            status="DRAFT",
            notes=command.notes,
            created_by=command.user_id,
        )
        self.session.add(transfer)
        self.session.flush()
        for line in command.lines:
            quantity = self._positive_qty(line.quantity, "Transfer quantity")
            product = products[line.product_id]
            if product.batch_tracking_enabled and line.source_batch_id is None:
                raise ValidationError("Batch-tracked transfers require a source batch.")
            self.session.add(
                StockTransferItem(
                    company_id=self.company_id,
                    stock_transfer_id=transfer.id,
                    product_id=product.id,
                    source_batch_id=line.source_batch_id,
                    quantity=quantity,
                    created_by=command.user_id,
                )
            )
        self.session.commit()
        self.session.refresh(transfer)
        return transfer

    def dispatch_transfer(self, *, transfer_id: int, user_id: int) -> StockTransfer:
        """Move draft transfer quantities out of source-branch availability."""
        transfer = self._require_transfer(transfer_id, status="DRAFT", for_update=True)
        items = self._transfer_items(transfer.id)
        products = self._load_products({item.product_id for item in items}, for_update=True)
        inventory = InventoryService(self.session, self.company_id)
        for item in items:
            if item.source_batch_id is not None:
                batch = self._require_batch(
                    item.source_batch_id,
                    transfer.source_branch_id,
                    item.product_id,
                    for_update=True,
                )
                if batch.quantity_available < item.quantity:
                    raise InsufficientStockError("Transfer batch does not have enough stock.")
                batch.quantity_available = qty(batch.quantity_available - item.quantity)
                batch.row_version += 1
            inventory.record_movement(
                products[item.product_id],
                transfer.source_branch_id,
                -item.quantity,
                LedgerTxnType.TRANSFER_OUT.value,
                "stock_transfers",
                transfer.id,
                user_id,
                batch_id=item.source_batch_id,
            )
        transfer.status = "IN_TRANSIT"
        transfer.dispatched_at = datetime.now(UTC)
        transfer.updated_by = user_id
        self.session.commit()
        self.session.refresh(transfer)
        return transfer

    def receive_transfer(self, *, transfer_id: int, user_id: int) -> StockTransfer:
        """Accept an in-transit transfer and recreate its lots at the destination."""
        transfer = self._require_transfer(transfer_id, status="IN_TRANSIT", for_update=True)
        items = self._transfer_items(transfer.id)
        products = self._load_products({item.product_id for item in items}, for_update=True)
        inventory = InventoryService(self.session, self.company_id)
        for item in items:
            product = products[item.product_id]
            destination_batch: StockBatch | None = None
            if item.source_batch_id is not None:
                source = self._require_batch(
                    item.source_batch_id, transfer.source_branch_id, item.product_id
                )
                destination_batch = self._destination_batch(
                    source, transfer.destination_branch_id, user_id
                )
                destination_batch.quantity_received = qty(
                    destination_batch.quantity_received + item.quantity
                )
                destination_batch.quantity_available = qty(
                    destination_batch.quantity_available + item.quantity
                )
                destination_batch.row_version += 1
            inventory.record_movement(
                product,
                transfer.destination_branch_id,
                item.quantity,
                LedgerTxnType.TRANSFER_IN.value,
                "stock_transfers",
                transfer.id,
                user_id,
                batch_id=destination_batch.id if destination_batch is not None else None,
            )
            item.received_quantity = item.quantity
            item.updated_by = user_id
        transfer.status = "RECEIVED"
        transfer.received_at = datetime.now(UTC)
        transfer.updated_by = user_id
        self.session.commit()
        self.session.refresh(transfer)
        return transfer

    def reorder_suggestions(
        self, *, branch_id: int, as_of: date, sales_days: int = 30
    ) -> tuple[ReorderSuggestion, ...]:
        """Suggest replenishment from sales velocity, lead time, and safety stock."""
        self._require_branch(branch_id)
        if sales_days < 1 or sales_days > 3650:
            raise ValidationError("Sales velocity window must be between 1 and 3650 days.")
        start = as_of - timedelta(days=sales_days - 1)
        sold = {
            int(row[0]): qty(row[1])
            for row in self.session.execute(
                select(SaleItem.product_id, func.sum(SaleItem.quantity))
                .join(Sale, Sale.id == SaleItem.sale_id)
                .where(
                    Sale.company_id == self.company_id,
                    SaleItem.company_id == self.company_id,
                    Sale.branch_id == branch_id,
                    Sale.business_date.between(start, as_of),
                    Sale.sale_status == "COMPLETED",
                    Sale.deleted_at.is_(None),
                    SaleItem.deleted_at.is_(None),
                )
                .group_by(SaleItem.product_id)
            )
        }
        products = self.session.scalars(
            select(Product).where(
                Product.company_id == self.company_id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
                Product.is_inventory_tracked.is_(True),
            )
        )
        suggestions: list[ReorderSuggestion] = []
        for product in products:
            velocity = qty(sold.get(product.id, ZERO_QTY) / Decimal(sales_days))
            target = qty(velocity * product.lead_time_days + product.safety_stock)
            on_hand = self._branch_balance(branch_id, product.id)
            suggested = qty(max(ZERO_QTY, target - on_hand))
            if suggested > ZERO_QTY:
                suggestions.append(
                    ReorderSuggestion(
                        product_id=product.id,
                        sku=product.sku,
                        on_hand=on_hand,
                        daily_velocity=velocity,
                        lead_time_days=product.lead_time_days,
                        safety_stock=qty(product.safety_stock),
                        suggested_quantity=suggested,
                    )
                )
        return tuple(sorted(suggestions, key=lambda row: (-row.suggested_quantity, row.product_id)))

    def stock_value(self, *, branch_id: int) -> tuple[StockValueRow, ...]:
        """Value one branch at both weighted cost and current retail price."""
        self._require_branch(branch_id)
        products = self.session.scalars(
            select(Product).where(
                Product.company_id == self.company_id,
                Product.deleted_at.is_(None),
                Product.is_inventory_tracked.is_(True),
            )
        )
        rows = []
        for product in products:
            balance = self._branch_balance(branch_id, product.id)
            if balance == ZERO_QTY:
                continue
            rows.append(
                StockValueRow(
                    product_id=product.id,
                    sku=product.sku,
                    quantity=balance,
                    cost_value=money(balance * product.cost_price),
                    retail_value=money(balance * product.selling_price),
                )
            )
        return tuple(rows)

    def _fefo_batches(
        self,
        *,
        product: Product,
        branch_id: int,
        on_date: date,
        expired_policy: str,
        for_update: bool,
    ) -> tuple[StockBatch, ...]:
        if product.company_id != self.company_id or not product.batch_tracking_enabled:
            raise ValidationError("FEFO allocation requires an active batch-tracked product.")
        policy = expired_policy.strip().upper()
        if policy not in {"BLOCK", "WARN"}:
            raise ValidationError("Expired-stock policy must be BLOCK or WARN.")
        statement = select(StockBatch).where(
            StockBatch.company_id == self.company_id,
            StockBatch.branch_id == branch_id,
            StockBatch.product_id == product.id,
            StockBatch.deleted_at.is_(None),
            StockBatch.is_active.is_(True),
            StockBatch.quantity_available > ZERO_QTY,
        )
        if policy == "BLOCK":
            statement = statement.where(
                (StockBatch.expiry_date.is_(None)) | (StockBatch.expiry_date >= on_date)
            )
        statement = statement.order_by(
            case((StockBatch.expiry_date.is_(None), 1), else_=0),
            StockBatch.expiry_date,
            StockBatch.id,
        )
        if for_update:
            statement = statement.with_for_update()
        return tuple(self.session.scalars(statement))

    def _branch_balance(self, branch_id: int, product_id: int) -> Decimal:
        return qty(
            self.session.scalar(
                select(func.coalesce(func.sum(StockLedger.quantity), 0)).where(
                    StockLedger.company_id == self.company_id,
                    StockLedger.branch_id == branch_id,
                    StockLedger.product_id == product_id,
                    StockLedger.deleted_at.is_(None),
                )
            )
        )

    def _add_count_line(
        self,
        audit: StockAudit,
        product_id: int,
        batch_id: int | None,
        expected: Decimal,
        user_id: int,
    ) -> None:
        self.session.add(
            StockAuditItem(
                company_id=self.company_id,
                stock_audit_id=audit.id,
                product_id=product_id,
                batch_id=batch_id,
                expected_quantity=expected,
                created_by=user_id,
            )
        )

    def _require_audit(self, audit_id: int, *, status: str, for_update: bool) -> StockAudit:
        statement = select(StockAudit).where(
            StockAudit.id == audit_id,
            StockAudit.company_id == self.company_id,
            StockAudit.status == status,
            StockAudit.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        audit = self.session.scalar(statement)
        if audit is None:
            raise EntityNotFoundError(f"{status.title()} stock audit was not found.")
        return audit

    def _require_transfer(
        self, transfer_id: int, *, status: str, for_update: bool
    ) -> StockTransfer:
        statement = select(StockTransfer).where(
            StockTransfer.id == transfer_id,
            StockTransfer.company_id == self.company_id,
            StockTransfer.status == status,
            StockTransfer.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        transfer = self.session.scalar(statement)
        if transfer is None:
            raise EntityNotFoundError(f"{status.title()} stock transfer was not found.")
        return transfer

    def _transfer_items(self, transfer_id: int) -> tuple[StockTransferItem, ...]:
        return tuple(
            self.session.scalars(
                select(StockTransferItem).where(
                    StockTransferItem.company_id == self.company_id,
                    StockTransferItem.stock_transfer_id == transfer_id,
                    StockTransferItem.deleted_at.is_(None),
                )
            )
        )

    def _require_batch(
        self,
        batch_id: int,
        branch_id: int,
        product_id: int,
        *,
        for_update: bool = False,
    ) -> StockBatch:
        statement = select(StockBatch).where(
            StockBatch.id == batch_id,
            StockBatch.company_id == self.company_id,
            StockBatch.branch_id == branch_id,
            StockBatch.product_id == product_id,
            StockBatch.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        batch = self.session.scalar(statement)
        if batch is None:
            raise EntityNotFoundError("Stock batch was not found.")
        return batch

    def _destination_batch(
        self, source: StockBatch, destination_branch_id: int, user_id: int
    ) -> StockBatch:
        batch = self.session.scalar(
            select(StockBatch)
            .where(
                StockBatch.company_id == self.company_id,
                StockBatch.branch_id == destination_branch_id,
                StockBatch.product_id == source.product_id,
                StockBatch.batch_number == source.batch_number,
                StockBatch.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if batch is not None:
            return batch
        batch = StockBatch(
            company_id=self.company_id,
            branch_id=destination_branch_id,
            product_id=source.product_id,
            batch_number=source.batch_number,
            mfg_date=source.mfg_date,
            expiry_date=source.expiry_date,
            cost_price=source.cost_price,
            selling_price=source.selling_price,
            quantity_received=ZERO_QTY,
            quantity_available=ZERO_QTY,
            created_by=user_id,
        )
        self.session.add(batch)
        self.session.flush()
        return batch

    def _require_company(self) -> Company:
        company = self.session.scalar(
            select(Company).where(
                Company.id == self.company_id,
                Company.deleted_at.is_(None),
                Company.is_active.is_(True),
            )
        )
        if company is None:
            raise EntityNotFoundError("Company was not found.")
        return company

    def _require_branch(self, branch_id: int) -> Branch:
        branch = self.session.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == self.company_id,
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
        )
        if branch is None:
            raise EntityNotFoundError("Branch was not found.")
        return branch

    def _require_product(self, product_id: int) -> Product:
        product = self.session.scalar(
            select(Product).where(
                Product.id == product_id,
                Product.company_id == self.company_id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
            )
        )
        if product is None:
            raise EntityNotFoundError("Product was not found.")
        return product

    def _load_products(
        self, product_ids: set[int], *, for_update: bool = False
    ) -> dict[int, Product]:
        statement = select(Product).where(
            Product.company_id == self.company_id,
            Product.id.in_(sorted(product_ids)),
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
        )
        if for_update:
            statement = statement.order_by(Product.id).with_for_update()
        products = {product.id: product for product in self.session.scalars(statement)}
        if products.keys() != product_ids:
            raise EntityNotFoundError("One or more products were not found.")
        return products

    def _require_command_company(self, company_id: int) -> None:
        if company_id != self.company_id:
            raise ValidationError("Command company does not match the active tenant.")

    @staticmethod
    def _money(value: object, label: str) -> Decimal:
        try:
            return money(value)
        except ValueError as exc:
            raise ValidationError(f"{label} must be numeric.") from exc

    @staticmethod
    def _positive_qty(value: object, label: str) -> Decimal:
        result = InventoryDepthService._nonnegative_qty(value, label)
        if result <= ZERO_QTY:
            raise ValidationError(f"{label} must be greater than zero.")
        return result

    @staticmethod
    def _nonnegative_qty(value: object, label: str) -> Decimal:
        try:
            result = qty(to_decimal(value))
        except ValueError as exc:
            raise ValidationError(f"{label} must be numeric.") from exc
        if result < ZERO_QTY:
            raise ValidationError(f"{label} cannot be negative.")
        return result
