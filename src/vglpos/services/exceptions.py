"""Typed service failures suitable for RFC 7807 responses."""

from __future__ import annotations


class ServiceError(Exception):
    """Base business failure carrying stable HTTP and problem-type metadata."""

    status_code = 500
    error_type = "service-error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ValidationError(ServiceError):
    """Reject malformed or internally inconsistent command data."""

    status_code = 400
    error_type = "validation-error"


class EntityNotFoundError(ServiceError):
    """Hide whether an identifier exists outside the active tenant."""

    status_code = 404
    error_type = "entity-not-found"


class ConflictError(ServiceError):
    """Report a valid command that conflicts with persisted state."""

    status_code = 409
    error_type = "conflict"


class InvoiceNumberError(ConflictError):
    """Report missing, exhausted, or invalid fiscal number series."""

    error_type = "invoice-number-error"


class InsufficientStockError(ConflictError):
    """Prevent an inventory-tracked product from becoming negative."""

    error_type = "insufficient-stock"


class CheckoutError(ConflictError):
    """Wrap a database conflict while preserving checkout atomicity."""

    error_type = "checkout-conflict"


class InvalidPaymentError(ServiceError):
    """Reject insufficient tender or change funded by non-cash methods."""

    status_code = 422
    error_type = "invalid-payment"


class ReturnQuantityError(ConflictError):
    """Prevent aggregate returns from exceeding an original sale line."""

    error_type = "return-quantity-conflict"


class ShiftError(ConflictError):
    """Report invalid cash-drawer lifecycle transitions."""

    error_type = "shift-conflict"


class AuthenticationError(ServiceError):
    """Return one generic credential failure without identity enumeration."""

    status_code = 401
    error_type = "authentication-failed"


class AuthorizationError(ServiceError):
    """Reject an authenticated principal lacking the required authority."""

    status_code = 403
    error_type = "authorization-failed"


class SessionLockedError(AuthorizationError):
    """Require counter PIN authentication before a locked screen resumes."""

    status_code = 423
    error_type = "session-locked"
