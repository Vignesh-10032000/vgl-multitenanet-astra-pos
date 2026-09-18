"""Company tenant-root model."""

from __future__ import annotations

from sqlalchemy import Boolean, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import AuditMixin, SurrogateKeyMixin
from vglpos.extensions import Base


class Company(AuditMixin, SurrogateKeyMixin, Base):
    """Legal entity that owns all tenant-scoped records."""

    __tablename__ = "companies"
    __table_args__ = (
        Index(
            "uq_companies_login_code",
            "login_code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND login_code IS NOT NULL"),
            sqlite_where=text("deleted_at IS NULL AND login_code IS NOT NULL"),
        ),
        Index(
            "uq_companies_gstin",
            "gstin",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND gstin IS NOT NULL"),
            sqlite_where=text("deleted_at IS NULL AND gstin IS NOT NULL"),
        ),
        Index(
            "idx_companies_active",
            "is_active",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    login_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cin: Mapped[str | None] = mapped_column(String(21), nullable=True)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="INR", server_default=text("'INR'"), nullable=False
    )
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
