"""Tenant isolation and update behavior for the Phase 5 store profile."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from vglpos.services.exceptions import EntityNotFoundError, ValidationError
from vglpos.services.store_profile_service import (
    StoreProfileService,
    UpdateStoreProfileCommand,
)

from .conftest import ServiceContext


def _command(context: ServiceContext, **overrides: object) -> UpdateStoreProfileCommand:
    values: dict[str, object] = {
        "company_id": context.company.id,
        "branch_id": context.branch.id,
        "user_id": context.cashier.id,
        "name": "Updated Test Store",
        "legal_name": "Updated Test Store Private Limited",
        "gstin": None,
        "phone": "9000000000",
        "address_line1": "2 Updated Street",
        "address_line2": "First Floor",
        "city": "Madurai",
        "state": "Tamil Nadu",
        "postal_code": "625001",
    }
    values.update(overrides)
    return UpdateStoreProfileCommand(**values)  # type: ignore[arg-type]


def test_store_profile_update_is_atomic_and_printable(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = StoreProfileService(
        service_session,
        service_context.company.id,
        branch_id=service_context.branch.id,
    )

    profile = service.update(_command(service_context))

    assert profile.name == "Updated Test Store"
    assert profile.legal_name == "Updated Test Store Private Limited"
    assert profile.phone == "9000000000"
    assert profile.address == "2 Updated Street, First Floor, Madurai, Tamil Nadu, 625001"
    assert service.get() == profile


def test_store_profile_rejects_mismatched_authenticated_context(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = StoreProfileService(
        service_session,
        service_context.company.id,
        branch_id=service_context.branch.id,
    )

    with pytest.raises(ValidationError, match="Authenticated company"):
        service.update(_command(service_context, company_id=service_context.company.id + 1))


def test_store_profile_hides_unknown_tenant(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = StoreProfileService(
        service_session,
        service_context.company.id + 1,
        branch_id=service_context.branch.id,
    )

    with pytest.raises(EntityNotFoundError, match="Store profile"):
        service.get()
