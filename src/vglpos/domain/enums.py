"""Stable domain vocabulary stored as strings in PostgreSQL."""

from __future__ import annotations

from enum import StrEnum


class PaymentMethod(StrEnum):
    """Supported sale and tender payment methods."""

    CASH = "CASH"
    CARD = "CARD"
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"
    CREDIT = "CREDIT"
    LOYALTY = "LOYALTY"
    OTHER = "OTHER"


class SaleStatus(StrEnum):
    """Lifecycle states for an immutable fiscal sale document."""

    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    PARTIALLY_RETURNED = "PARTIALLY_RETURNED"
    RETURNED = "RETURNED"


class SupplyType(StrEnum):
    """GST supply modes controlling CGST/SGST versus IGST."""

    INTRASTATE = "INTRASTATE"
    INTERSTATE = "INTERSTATE"


class LedgerTxnType(StrEnum):
    """Inventory movements accepted by the append-only stock ledger."""

    OPENING = "OPENING"
    PURCHASE = "PURCHASE"
    PURCHASE_RETURN = "PURCHASE_RETURN"
    SALE = "SALE"
    SALE_RETURN = "SALE_RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    RESERVATION = "RESERVATION"
    RESERVATION_RELEASE = "RESERVATION_RELEASE"


class ShiftStatus(StrEnum):
    """Cash-drawer shift states."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class DocType(StrEnum):
    """Fiscal document series types."""

    SALE = "SALE"
    CREDIT_NOTE = "CREDIT_NOTE"
    PURCHASE = "PURCHASE"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    GOODS_RECEIPT = "GOODS_RECEIPT"
    DEBIT_NOTE = "DEBIT_NOTE"
    STOCK_TRANSFER = "STOCK_TRANSFER"


class ReturnReason(StrEnum):
    """Stable return-reason codes retained on credit notes."""

    DEFECTIVE = "DEFECTIVE"
    DAMAGED = "DAMAGED"
    WRONG_ITEM = "WRONG_ITEM"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"
    OTHER = "OTHER"
