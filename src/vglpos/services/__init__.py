"""Business services independent of Flask request state."""

from vglpos.services.catalog_service import CatalogService
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
    QuoteCommand,
)
from vglpos.services.customer_service import CustomerService
from vglpos.services.inventory_service import InventoryService
from vglpos.services.invoice_number_service import InvoiceNumberService
from vglpos.services.report_service import ReportService
from vglpos.services.return_service import CreateCreditNoteCommand, ReturnLineCommand, ReturnService
from vglpos.services.sales_service import SalesService
from vglpos.services.shift_service import (
    CashMovementCommand,
    CloseShiftCommand,
    OpenShiftCommand,
    ShiftService,
)

__all__ = [
    "CashMovementCommand",
    "CatalogService",
    "CheckoutCommand",
    "CheckoutLineCommand",
    "CheckoutService",
    "CloseShiftCommand",
    "CreateCreditNoteCommand",
    "CustomerService",
    "InventoryService",
    "InvoiceNumberService",
    "OpenShiftCommand",
    "PaymentCommand",
    "QuoteCommand",
    "ReportService",
    "ReturnLineCommand",
    "ReturnService",
    "SalesService",
    "ShiftService",
]
