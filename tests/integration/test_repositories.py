"""Tenant and keyset invariants for Phase 1D repositories."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from vglpos.domain.models import Product, ProductBarcode
from vglpos.repositories import (
    CustomerRepository,
    ProductRepository,
    SaleRepository,
    ShiftRepository,
    StockRepository,
    UserRepository,
)

from .conftest import ServiceContext, seed_service_context


def test_repository_refuses_to_run_without_company_id(service_session: Session) -> None:
    with pytest.raises(ValueError, match="company_id is required"):
        ProductRepository(service_session, 0)


def test_repository_never_reads_another_company(
    service_session: Session, service_context: ServiceContext
) -> None:
    other = seed_service_context(service_session, company_name="Other Tenant")

    own_repository = ProductRepository(service_session, service_context.company.id)
    other_repository = ProductRepository(service_session, other.company.id)
    assert own_repository.get(other.product.id) is None
    assert other_repository.get(service_context.product.id) is None


def test_repository_keyset_pagination_and_soft_delete(
    service_session: Session, service_context: ServiceContext
) -> None:
    for index in range(3):
        service_session.add(
            Product(
                company_id=service_context.company.id,
                sku=f"SKU-{index + 2:03d}",
                name=f"Product {index + 2}",
                tax_rate_id=service_context.tax_rate.id,
                cost_price=Decimal("10.00"),
                selling_price=Decimal("20.00"),
                mrp=Decimal("20.00"),
            )
        )
    service_session.commit()
    repository = ProductRepository(service_session, service_context.company.id)

    first = repository.list(limit=2)
    second = repository.list(cursor=first.next_cursor, limit=2)

    assert len(first) == 2
    assert len(second) == 2
    assert {product.id for product in first}.isdisjoint(product.id for product in second)
    repository.soft_delete(first[0].id, user_id=service_context.cashier.id)
    service_session.commit()
    assert repository.get(first[0].id) is None
    assert repository.count() == 3


def test_product_barcode_lookup_uses_primary_and_alternate_codes(
    service_session: Session, service_context: ServiceContext
) -> None:
    alternate = ProductBarcode(
        company_id=service_context.company.id,
        product_id=service_context.product.id,
        barcode="ALT-001",
    )
    service_session.add(alternate)
    service_session.commit()
    repository = ProductRepository(service_session, service_context.company.id)

    assert (
        repository.find_by_barcode(service_context.product.barcode or "") == service_context.product
    )
    assert repository.find_by_barcode("ALT-001") == service_context.product
    assert repository.search("Test Prod") == (service_context.product,)


def test_all_specialized_repositories_require_tenant_scope(
    service_session: Session, service_context: ServiceContext
) -> None:
    repositories = (
        CustomerRepository,
        SaleRepository,
        StockRepository,
        UserRepository,
        ShiftRepository,
    )
    for repository_type in repositories:
        repository = repository_type(service_session, service_context.company.id)
        assert repository.company_id == service_context.company.id
