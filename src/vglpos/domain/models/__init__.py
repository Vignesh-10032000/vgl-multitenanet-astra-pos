"""Complete Phase 1B model registry."""

from __future__ import annotations

from vglpos.domain.models.branch import Branch
from vglpos.domain.models.catalog import (
    Category,
    HsnCode,
    Product,
    ProductBarcode,
    ProductPriceHistory,
    TaxRate,
)
from vglpos.domain.models.company import Company
from vglpos.domain.models.documents import (
    CreditNote,
    CreditNoteItem,
    CreditNoteItemBatch,
    DocumentSeries,
    Sale,
    SaleItem,
    SaleItemBatch,
    SalePayment,
)
from vglpos.domain.models.identity import Permission, Role, RolePermission, User, UserRole
from vglpos.domain.models.inventory import (
    GoodsReceipt,
    GoodsReceiptItem,
    Purchase,
    PurchaseItem,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReturn,
    PurchaseReturnItem,
    StockAudit,
    StockAuditItem,
    StockBatch,
    StockLedger,
    StockLedgerEntry,
    StockTransfer,
    StockTransferItem,
    SupplierLedger,
)
from vglpos.domain.models.migration import LegacyIdMap
from vglpos.domain.models.operations import (
    AuditLog,
    CashMovement,
    HeldBill,
    ReportJob,
    Shift,
    TerminalQuickKey,
)
from vglpos.domain.models.parties import Customer, LoyaltyLedger, Supplier
from vglpos.domain.models.terminal import Terminal

__all__ = [
    "AuditLog",
    "Branch",
    "CashMovement",
    "Category",
    "Company",
    "CreditNote",
    "CreditNoteItem",
    "CreditNoteItemBatch",
    "Customer",
    "DocumentSeries",
    "GoodsReceipt",
    "GoodsReceiptItem",
    "HeldBill",
    "HsnCode",
    "LegacyIdMap",
    "LoyaltyLedger",
    "Permission",
    "Product",
    "ProductBarcode",
    "ProductPriceHistory",
    "Purchase",
    "PurchaseItem",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseReturn",
    "PurchaseReturnItem",
    "ReportJob",
    "Role",
    "RolePermission",
    "Sale",
    "SaleItem",
    "SaleItemBatch",
    "SalePayment",
    "Shift",
    "StockAudit",
    "StockAuditItem",
    "StockBatch",
    "StockLedger",
    "StockLedgerEntry",
    "StockTransfer",
    "StockTransferItem",
    "Supplier",
    "SupplierLedger",
    "TaxRate",
    "Terminal",
    "TerminalQuickKey",
    "User",
    "UserRole",
]
