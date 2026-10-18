"""Tenant-scoped legal identity used by settings and fiscal receipts."""

from __future__ import annotations

import base64
import binascii
import io
import warnings
from dataclasses import dataclass

import structlog
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.models import Branch, Company
from vglpos.security.audit import record_audit_event
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
    logo_data_uri: str | None = None

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

    def update_logo(self, *, user_id: int, image_base64: str | None) -> StoreProfile:
        """Normalize small raster uploads so uploaded code and metadata never reach receipts."""
        company, branch = self._entities(for_update=True)
        normalized = None
        if image_base64 is not None:
            try:
                if len(image_base64) > 700_000:
                    raise ValueError("Image exceeds the upload limit.")
                content = base64.b64decode(image_base64, validate=True)
                if not content or len(content) > 512_000:
                    raise ValueError("Image exceeds the upload limit.")
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(content)) as source:
                        if source.format not in {"PNG", "JPEG", "WEBP"}:
                            raise ValueError("Unsupported image format.")
                        if source.width > 2048 or source.height > 2048:
                            raise ValueError("Image dimensions exceed 2048 pixels.")
                        source.load()
                        image = ImageOps.exif_transpose(source).convert("RGBA")
                        image.thumbnail((512, 256))
                        image.info.clear()
                        output = io.BytesIO()
                        image.save(output, format="PNG", optimize=True)
                        normalized = "data:image/png;base64," + base64.b64encode(
                            output.getvalue()
                        ).decode("ascii")
            except (
                ValueError,
                binascii.Error,
                OSError,
                UnidentifiedImageError,
                Image.DecompressionBombError,
                Image.DecompressionBombWarning,
            ) as exc:
                structlog.get_logger(__name__).warning(
                    "store_logo_rejected", company_id=self.company_id, user_id=user_id
                )
                raise ValidationError(
                    "Upload a valid PNG, JPEG or WebP up to 500 KB and 2048 x 2048 pixels."
                ) from exc
        company.logo_data_uri = normalized
        company.updated_by = user_id
        company.row_version += 1
        record_audit_event(
            self.session,
            company_id=self.company_id,
            user_id=user_id,
            action="STORE_LOGO_UPDATED",
            entity_type="Company",
            entity_id=company.id,
            new_values={"has_logo": normalized is not None},
        )
        self.session.commit()
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
            logo_data_uri=company.logo_data_uri,
        )
