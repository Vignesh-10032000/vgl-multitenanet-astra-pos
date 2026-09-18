"""Tenant-scoped repository API enforcing the data-access boundary."""

from vglpos.repositories.base import (
    BaseRepository,
    CursorPage,
    RepositoryEntityNotFoundError,
)
from vglpos.repositories.catalog import ProductRepository
from vglpos.repositories.documents import SaleRepository
from vglpos.repositories.identity import (
    AuthorizationContext,
    CompanyLoginRepository,
    UserRepository,
)
from vglpos.repositories.inventory import StockRepository
from vglpos.repositories.operations import ShiftRepository
from vglpos.repositories.parties import CustomerRepository

__all__ = [
    "AuthorizationContext",
    "BaseRepository",
    "CompanyLoginRepository",
    "CursorPage",
    "CustomerRepository",
    "ProductRepository",
    "RepositoryEntityNotFoundError",
    "SaleRepository",
    "ShiftRepository",
    "StockRepository",
    "UserRepository",
]
