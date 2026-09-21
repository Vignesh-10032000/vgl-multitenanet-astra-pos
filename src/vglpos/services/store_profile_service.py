"""Tenant-scoped legal identity used by settings and fiscal receipts."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.models import Branch, Company
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError


@dataclass(frozen=True, slots=True)
class StoreProfile:
    name: str
    legal_name: str
    gstin: str | None
    phone: str
    address_line1: str
    address_line2: str | None
    city: str
    state: str
    postal_code: str

    @property
    def address(self) -> str:
        """Return one printable address without losing structured fields."""
        return ", ".join(
            part
            for part in (
                self.address_line1,
                self.address_line2,
                self.city,
                self.state,
                self.postal_code,
            )
            if part
        )


@dataclass(frozen=True, slots=True)
class UpdateStoreProfileCommand:
    company_id: int
    branch_id: int | None
    user_id: int
    name: str
    legal_name: str
    gstin: str | None
    phone: str
    address_line1: str
    address_line2: str | None
    city: str
    state: str
    postal_code: str


class StoreProfileService:
    """Read and update the authenticated branch's legal receipt identity."""

    def __init__(self, session: Session, company_id: int, *, branch_id: int | None) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id
        self.branch_id = branch_id

    def get(self) -> StoreProfile:
        """Return only the authenticated company and selected branch identity."""
        company, branch = self._entities()
        return self._profile(company, branch)

    def update(self, cmd: UpdateStoreProfileCommand) -> StoreProfile:
        """Update legal receipt fields together so a bill never mixes identities."""
        if cmd.company_id != self.company_id or cmd.branch_id != self.branch_id or not cmd.user_id:
            raise ValidationError("Authenticated company, branch and user are required.")
        company, branch = self._entities(for_update=True)
        company.name = cmd.name.strip()
        company.legal_name = cmd.legal_name.strip()
        company.gstin = cmd.gstin
        company.contact_phone = cmd.phone.strip()
        company.address_line1 = cmd.address_line1.strip()
        company.address_line2 = cmd.address_line2.strip() if cmd.address_line2 else None
        company.city = cmd.city.strip()
        company.state = cmd.state.strip()
        company.postal_code = cmd.postal_code.strip()
        company.updated_by = cmd.user_id
        company.row_version += 1

        branch.gstin = cmd.gstin
        branch.phone = cmd.phone.strip()
        branch.address_line1 = cmd.address_line1.strip()
        branch.address_line2 = cmd.address_line2.strip() if cmd.address_line2 else None
        branch.city = cmd.city.strip()
        branch.state = cmd.state.strip()
        branch.postal_code = cmd.postal_code.strip()
        branch.updated_by = cmd.user_id
        branch.row_version += 1
        try:
            self.session.commit()
            self.session.refresh(company)
            self.session.refresh(branch)
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Store profile conflicts with an existing legal identity.") from exc
        return self._profile(company, branch)

    def _entities(self, *, for_update: bool = False) -> tuple[Company, Branch]:
        company_statement = select(Company).where(
            Company.id == self.company_id,
            Company.deleted_at.is_(None),
            Company.is_active.is_(True),
        )
        branch_statement = select(Branch).where(
            Branch.company_id == self.company_id,
            Branch.deleted_at.is_(None),
            Branch.is_active.is_(True),
        )
        if self.branch_id is not None:
            branch_statement = branch_statement.where(Branch.id == self.branch_id)
        branch_statement = branch_statement.order_by(Branch.is_head_office.desc(), Branch.id).limit(
            1
        )
        if for_update:
            company_statement = company_statement.with_for_update()
            branch_statement = branch_statement.with_for_update()
        company = self.session.scalar(company_statement)
        branch = self.session.scalar(branch_statement)
        if company is None or branch is None:
            raise EntityNotFoundError("Store profile was not found.")
        return company, branch

    @staticmethod
    def _profile(company: Company, branch: Branch) -> StoreProfile:
        return StoreProfile(
            name=company.name,
            legal_name=company.legal_name,
            gstin=branch.gstin or company.gstin,
            phone=branch.phone,
            address_line1=branch.address_line1,
            address_line2=branch.address_line2,
            city=branch.city,
            state=branch.state,
            postal_code=branch.postal_code,
        )
