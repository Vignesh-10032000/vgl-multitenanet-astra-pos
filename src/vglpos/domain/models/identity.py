"""User, role, and permission persistence models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from vglpos.domain.models.base import BIGINT, GlobalEntity, TenantEntity


class User(TenantEntity):
    """Authenticated company user without exposing credential hashes in repr."""

    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_company_username",
            "company_id",
            "username",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_users_company_email",
            "company_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_users_company_id", "company_id"),
    )

    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    failed_login_attempts: Mapped[int] = mapped_column(
        default=0, server_default=text("0"), nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Role(TenantEntity):
    """Company-scoped collection of permission codes."""

    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(
            "max_discount_percent >= 0 AND max_discount_percent <= 100",
            name="ck_roles_max_discount_percent",
        ),
        Index(
            "uq_roles_company_name",
            "company_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    max_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=text("0.00"), nullable=False
    )


class Permission(GlobalEntity):
    """Global permission vocabulary seeded identically for every tenant."""

    __tablename__ = "permissions"
    __table_args__ = (
        Index(
            "uq_permissions_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)


class RolePermission(TenantEntity):
    """Many-to-many mapping from tenant roles to global permissions."""

    __tablename__ = "role_permissions"

    __table_args__ = (
        Index(
            "uq_role_permissions_pair",
            "role_id",
            "permission_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    role_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )


class UserRole(TenantEntity):
    """Assign one role to a user, optionally constrained to a branch."""

    __tablename__ = "user_roles"

    __table_args__ = (
        Index(
            "uq_user_roles_pair",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("branches.id", ondelete="CASCADE"), nullable=True
    )
