"""Single source of truth for Phase 2 permission and standard-role codes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    code: str
    description: str
    category: str


@dataclass(frozen=True, slots=True)
class StandardRoleDefinition:
    name: str
    description: str
    permissions: frozenset[str]
    max_discount_percent: Decimal = Decimal("0.00")


PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    PermissionDefinition("sale.create", "Complete a retail checkout", "sale"),
    PermissionDefinition("sale.view", "View sales and invoice details", "sale"),
    PermissionDefinition("sale.void", "Void a completed sale", "sale"),
    PermissionDefinition("sale.discount", "Apply a sale discount", "sale"),
    PermissionDefinition("sale.price_override", "Override a product price", "sale"),
    PermissionDefinition("product.view", "View product catalogue data", "product"),
    PermissionDefinition("product.create", "Create products", "product"),
    PermissionDefinition("product.edit", "Edit products", "product"),
    PermissionDefinition("product.delete", "Soft-delete products", "product"),
    PermissionDefinition("stock.adjust", "Record authorised stock adjustments", "stock"),
    PermissionDefinition("stock.view", "View stock balances and movements", "stock"),
    PermissionDefinition("stock.audit", "Conduct and post physical stock counts", "stock"),
    PermissionDefinition("stock.transfer", "Move stock between branches", "stock"),
    PermissionDefinition("stock.reorder", "View stock replenishment suggestions", "stock"),
    PermissionDefinition("customer.view", "View customer records", "customer"),
    PermissionDefinition("customer.create", "Create customer records", "customer"),
    PermissionDefinition("customer.edit", "Edit customer records", "customer"),
    PermissionDefinition("customer.export", "Export customer records", "customer"),
    PermissionDefinition("return.create", "Create returns and credit notes", "return"),
    PermissionDefinition("return.approve", "Approve returns and credit notes", "return"),
    PermissionDefinition("report.view", "View operational reports", "report"),
    PermissionDefinition("report.gst", "View GST reports", "report"),
    PermissionDefinition("report.export", "Export statutory reports", "report"),
    PermissionDefinition("shift.open", "Open a cashier shift", "shift"),
    PermissionDefinition("shift.close", "Close and reconcile a shift", "shift"),
    PermissionDefinition("cash.move", "Record a cash movement", "cash"),
    PermissionDefinition("user.manage", "Manage company users and roles", "administration"),
    PermissionDefinition("settings.manage", "Manage company settings", "administration"),
    PermissionDefinition("einvoice.generate", "Generate an e-invoice", "einvoice"),
    PermissionDefinition("einvoice.view", "View e-invoice compliance state", "einvoice"),
    PermissionDefinition("einvoice.retry", "Retry failed e-invoices", "einvoice"),
    PermissionDefinition("einvoice.cancel", "Cancel generated IRNs", "einvoice"),
    PermissionDefinition("eway.generate", "Generate an e-way bill", "einvoice"),
    PermissionDefinition("purchase.create", "Create supplier purchases", "purchase"),
    PermissionDefinition("purchase.approve", "Approve supplier purchases", "purchase"),
    PermissionDefinition("purchase.view", "View supplier purchase documents", "purchase"),
    PermissionDefinition("purchase.receive", "Receive purchase orders", "purchase"),
    PermissionDefinition("purchase.invoice", "Match and post supplier invoices", "purchase"),
    PermissionDefinition("purchase.return", "Create purchase debit notes", "purchase"),
    PermissionDefinition("supplier.view", "View supplier masters and ledgers", "purchase"),
    PermissionDefinition("supplier.create", "Create supplier masters", "purchase"),
    PermissionDefinition("supplier.pay", "Record supplier payments", "purchase"),
)

KNOWN_PERMISSION_CODES: frozenset[str] = frozenset(
    definition.code for definition in PERMISSION_DEFINITIONS
)

STANDARD_ROLES: tuple[StandardRoleDefinition, ...] = (
    StandardRoleDefinition(
        "SUPER_ADMIN",
        "Company administrator who controls administrator access",
        KNOWN_PERMISSION_CODES,
    ),
    StandardRoleDefinition(
        "ADMIN",
        "Company administrator who manages store operations and staff",
        KNOWN_PERMISSION_CODES,
    ),
    StandardRoleDefinition("OWNER", "Company owner with every permission", KNOWN_PERMISSION_CODES),
    StandardRoleDefinition(
        "MANAGER",
        "Store manager without company ownership controls",
        KNOWN_PERMISSION_CODES - {"user.manage", "settings.manage"},
    ),
    StandardRoleDefinition(
        "CASHIER",
        "Counter checkout operator",
        frozenset(
            {
                "sale.create",
                "sale.view",
                "product.view",
                "return.create",
                "shift.open",
                "shift.close",
                "cash.move",
                "customer.view",
                "customer.create",
            }
        ),
    ),
    StandardRoleDefinition(
        "STOCK_CLERK",
        "Catalogue, purchasing, and stock operator",
        frozenset(
            {
                "product.view",
                "product.create",
                "product.edit",
                "stock.view",
                "stock.adjust",
                "stock.audit",
                "stock.transfer",
                "stock.reorder",
                "purchase.create",
                "purchase.view",
                "purchase.receive",
                "purchase.invoice",
                "purchase.return",
                "supplier.view",
                "supplier.create",
            }
        ),
    ),
    StandardRoleDefinition(
        "ACCOUNTANT",
        "Financial reporting and export operator",
        frozenset(
            {
                "sale.view",
                "customer.export",
                "report.view",
                "report.gst",
                "report.export",
                "purchase.view",
                "supplier.view",
                "supplier.pay",
                "einvoice.generate",
                "einvoice.view",
                "einvoice.retry",
                "einvoice.cancel",
                "eway.generate",
            }
        ),
    ),
    StandardRoleDefinition(
        "AUDITOR",
        "Read-only operational reviewer",
        frozenset(
            {
                "sale.view",
                "product.view",
                "stock.view",
                "customer.view",
                "customer.export",
                "report.view",
                "report.gst",
                "report.export",
                "purchase.view",
                "supplier.view",
                "einvoice.view",
            }
        ),
    ),
)
