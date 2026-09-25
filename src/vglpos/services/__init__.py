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
from vglpos.services.financial_report_service import FinancialReportService
from vglpos.services.inventory_depth_service import (
    CreateTransferCommand,
    InventoryDepthService,
    StockCountLineCommand,
    TransferLineCommand,
    VariantCommand,
)
from vglpos.services.inventory_service import InventoryService
from vglpos.services.invoice_number_service import InvoiceNumberService
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
from vglpos.services.report_export_service import ReportExportService
from vglpos.services.report_job_service import ReportJobService
from vglpos.services.report_service import ReportService
from vglpos.services.return_service import CreateCreditNoteCommand, ReturnLineCommand, ReturnService
from vglpos.services.sales_service import SalesService
from vglpos.services.shift_service import (
    CashMovementCommand,
    CloseShiftCommand,
    OpenShiftCommand,
    ShiftService,
)
from vglpos.services.statutory_report_service import StatutoryReportService

__all__ = [
    "CashMovementCommand",
    "CatalogService",
    "CheckoutCommand",
    "CheckoutLineCommand",
    "CheckoutService",
    "CloseShiftCommand",
    "CreateCreditNoteCommand",
    "CreateGoodsReceiptCommand",
    "CreatePurchaseOrderCommand",
    "CreateTransferCommand",
    "CustomerService",
    "FinancialReportService",
    "GoodsReceiptLineCommand",
    "InventoryDepthService",
    "InventoryService",
    "InvoiceNumberService",
    "OpenShiftCommand",
    "PaymentCommand",
    "PostPurchaseInvoiceCommand",
    "PurchaseInvoiceLineCommand",
    "PurchaseOrderLineCommand",
    "PurchaseReturnCommand",
    "PurchaseReturnLineCommand",
    "PurchaseService",
    "QuoteCommand",
    "ReportExportService",
    "ReportJobService",
    "ReportService",
    "ReturnLineCommand",
    "ReturnService",
    "SalesService",
    "ShiftService",
    "StatutoryReportService",
    "StockCountLineCommand",
    "SupplierCommand",
    "SupplierPaymentCommand",
    "TransferLineCommand",
    "VariantCommand",
]
