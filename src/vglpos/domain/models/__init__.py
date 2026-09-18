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
    DocumentSeries,
    Sale,
    SaleItem,
    SalePayment,
)
from vglpos.domain.models.identity import Permission, Role, RolePermission, User, UserRole
from vglpos.domain.models.inventory import (
    Purchase,
    PurchaseItem,
    StockBatch,
    StockLedger,
    StockLedgerEntry,
)
from vglpos.domain.models.migration import LegacyIdMap
from vglpos.domain.models.operations import AuditLog, CashMovement, Shift
from vglpos.domain.models.parties import Customer, Supplier
from vglpos.domain.models.terminal import Terminal

__all__ = [
    "AuditLog",
    "Branch",
    "CashMovement",
    "Category",
    "Company",
    "CreditNote",
    "CreditNoteItem",
    "Customer",
    "DocumentSeries",
    "HsnCode",
    "LegacyIdMap",
    "Permission",
    "Product",
    "ProductBarcode",
    "ProductPriceHistory",
    "Purchase",
    "PurchaseItem",
    "Role",
    "RolePermission",
    "Sale",
    "SaleItem",
    "SalePayment",
    "Shift",
    "StockBatch",
    "StockLedger",
    "StockLedgerEntry",
    "Supplier",
    "TaxRate",
    "Terminal",
    "User",
    "UserRole",
]
