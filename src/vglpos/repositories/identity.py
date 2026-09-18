"""User persistence queries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from vglpos.domain.models import (
    Branch,
    Company,
    Permission,
    Role,
    RolePermission,
    Terminal,
    User,
    UserRole,
)
from vglpos.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """Resolved role facts embedded into a short-lived access token."""

    role_names: tuple[str, ...]
    permissions: frozenset[str]
    max_discount_percent: Decimal


class CompanyLoginRepository:
    """Resolve the public tenant code before entering company-scoped queries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_login_code(self, login_code: str) -> Company | None:
        """Resolve one active tenant by its non-secret normalized login code."""
        return self.session.scalar(
            select(Company).where(
                Company.login_code == login_code.strip().upper(),
                Company.is_active.is_(True),
                Company.deleted_at.is_(None),
            )
        )


class UserRepository(BaseRepository[User]):
    """Query live user identities within one company."""

    model = User

    def find_by_username(self, username: str) -> User | None:
        """Resolve a username under the tenant uniqueness boundary."""
        return self.session.scalar(self._base_query().where(User.username == username))

    def find_by_email(self, email: str) -> User | None:
        """Resolve a normalized email under the tenant uniqueness boundary."""
        return self.session.scalar(self._base_query().where(User.email == email))

    def authorization_context(self, user_id: int, *, branch_id: int | None) -> AuthorizationContext:
        """Collect only roles applicable globally or to the selected branch."""
        branch_predicate: ColumnElement[bool] = UserRole.branch_id.is_(None)
        if branch_id is not None:
            branch_predicate = or_(branch_predicate, UserRole.branch_id == branch_id)
        role_rows = list(
            self.session.execute(
                select(Role.id, Role.name, Role.max_discount_percent)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(
                    UserRole.company_id == self.company_id,
                    UserRole.user_id == user_id,
                    UserRole.deleted_at.is_(None),
                    Role.company_id == self.company_id,
                    Role.deleted_at.is_(None),
                    branch_predicate,
                )
                .order_by(Role.name)
            )
        )
        role_ids = tuple(int(row.id) for row in role_rows)
        permissions: frozenset[str] = frozenset()
        if role_ids:
            permissions = frozenset(
                self.session.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .where(
                        RolePermission.company_id == self.company_id,
                        RolePermission.role_id.in_(role_ids),
                        RolePermission.deleted_at.is_(None),
                        Permission.deleted_at.is_(None),
                    )
                )
            )
        max_discount = max(
            (Decimal(str(row.max_discount_percent)) for row in role_rows),
            default=Decimal("0.00"),
        )
        return AuthorizationContext(
            role_names=tuple(str(row.name) for row in role_rows),
            permissions=permissions,
            max_discount_percent=max_discount,
        )

    def branch_exists(self, branch_id: int) -> bool:
        """Validate a branch without revealing another tenant's identifiers."""
        return (
            self.session.scalar(
                select(Branch.id).where(
                    Branch.id == branch_id,
                    Branch.company_id == self.company_id,
                    Branch.is_active.is_(True),
                    Branch.deleted_at.is_(None),
                )
            )
            is not None
        )

    def terminal_exists(self, terminal_id: int, *, branch_id: int | None) -> bool:
        """Validate terminal ownership and its selected branch when one is supplied."""
        statement = select(Terminal.id).where(
            Terminal.id == terminal_id,
            Terminal.company_id == self.company_id,
            Terminal.is_active.is_(True),
            Terminal.deleted_at.is_(None),
        )
        if branch_id is not None:
            statement = statement.where(Terminal.branch_id == branch_id)
        return self.session.scalar(statement) is not None

    def terminal_branch_id(self, terminal_id: int) -> int | None:
        """Resolve a terminal's branch only inside the active company boundary."""
        return self.session.scalar(
            select(Terminal.branch_id).where(
                Terminal.id == terminal_id,
                Terminal.company_id == self.company_id,
                Terminal.is_active.is_(True),
                Terminal.deleted_at.is_(None),
            )
        )
