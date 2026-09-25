"""Reusable persistence mixins enforcing Phase 1B schema invariants."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, func, text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from vglpos.extensions import Base

# SQLite only auto-increments a column whose compiled type name is exactly
# INTEGER.  The variant preserves PostgreSQL BIGINT while keeping hermetic
# SQLite tests usable.
BIGINT = BigInteger().with_variant(Integer, "sqlite")


class SafeReprMixin:
    """Render only class and identifier so logs never expose money or PII."""

    id: Mapped[int]

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={getattr(self, 'id', None)!r}>"


class SurrogateKeyMixin(SafeReprMixin):
    """Provide the required BIGINT identity key to every persisted entity."""

    id: Mapped[int] = mapped_column(BIGINT, Identity(), primary_key=True)


class TenantMixin:
    """Make tenant ownership explicit and impossible to omit accidentally."""

    @declared_attr
    def company_id(cls) -> Mapped[int]:
        return mapped_column(
            BIGINT,
            ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        )


class AuditMixin:
    """Apply soft-delete and optimistic-concurrency columns consistently."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(
        BIGINT,
        ForeignKey("users.id", ondelete="RESTRICT", use_alter=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[int | None] = mapped_column(
        BIGINT,
        ForeignKey("users.id", ondelete="RESTRICT", use_alter=True),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(
        BIGINT,
        ForeignKey("users.id", ondelete="RESTRICT", use_alter=True),
        nullable=True,
    )
    row_version: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), default=1, nullable=False
    )


class TenantEntity(TenantMixin, AuditMixin, SurrogateKeyMixin, Base):
    """Abstract base for ordinary company-scoped entities."""

    __abstract__ = True


class ActorTenantEntity(TenantEntity):
    """Require an attributable creator for auditable business workflows."""

    __abstract__ = True

    created_by: Mapped[int] = mapped_column(
        BIGINT,
        ForeignKey("users.id", ondelete="RESTRICT", use_alter=True),
        nullable=False,
    )


class AuditedEntity(AuditMixin, SurrogateKeyMixin, Base):
    """Abstract base for audited entities owned through an aggregate root."""

    __abstract__ = True


class GlobalEntity(AuditedEntity):
    """Abstract base for the small set of global reference tables."""

    __abstract__ = True
