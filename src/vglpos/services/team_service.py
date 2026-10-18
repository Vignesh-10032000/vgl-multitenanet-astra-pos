"""Company-isolated team administration with explicit grant boundaries."""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.models import Company, Permission, Role, RolePermission, User, UserRole
from vglpos.repositories.identity import UserRepository
from vglpos.security.audit import record_audit_event
from vglpos.security.auth_service import AuthService
from vglpos.security.password import hash_password, hash_pin
from vglpos.security.permissions import STANDARD_ROLES
from vglpos.services.exceptions import (
    AuthorizationError,
    ConflictError,
    EntityNotFoundError,
    ValidationError,
)

_TOP_ROLES = frozenset({"OWNER", "SUPER_ADMIN"})
_ADMIN_ROLES = _TOP_ROLES | {"ADMIN"}


@dataclass(frozen=True, slots=True)
class TeamMember:
    id: int
    username: str
    email: str
    full_name: str
    roles: tuple[str, ...]
    is_active: bool
    mfa_enabled: bool


@dataclass(frozen=True, slots=True)
class TeamDirectory:
    members: list[TeamMember]
    assignable_roles: list[str]


@dataclass(frozen=True, slots=True)
class SaveTeamMember:
    username: str
    email: str
    full_name: str
    role: str
    actor_password: str
    is_active: bool = True
    password: str | None = None
    pin: str | None = None
    actor_mfa_code: str | None = None


class TeamService:
    """Keep grants, credential changes, revocation and audit in one transaction."""

    def __init__(self, session: Session, company_id: int, actor_id: int) -> None:
        if not company_id or not actor_id:
            raise ValueError("Authenticated company and actor are required.")
        self.session = session
        self.company_id = company_id
        self.actor_id = actor_id
        self.users = UserRepository(session, company_id)

    def directory(self) -> TeamDirectory:
        """Expose only this company's users and roles the actor may grant."""
        roles = self._assignable_roles()
        users = self.session.scalars(
            select(User)
            .where(User.company_id == self.company_id, User.deleted_at.is_(None))
            .order_by(User.full_name, User.id)
            .limit(500)
        )
        return TeamDirectory([self._member(user) for user in users], roles)

    def save(self, command: SaveTeamMember, *, user_id: int | None = None) -> TeamMember:
        """Prevent self escalation and revoke old sessions before altered access is used."""
        # Serialize company-wide account changes before checking grant boundaries.
        company = self.session.scalar(
            select(Company)
            .where(
                Company.id == self.company_id,
                Company.deleted_at.is_(None),
                Company.is_active.is_(True),
            )
            .with_for_update()
        )
        if company is None:
            raise EntityNotFoundError("The company is unavailable.")
        actor = AuthService(self.session).confirm_password(
            company_id=self.company_id,
            user_id=self.actor_id,
            password=command.actor_password,
            mfa_code=command.actor_mfa_code,
        )
        allowed = self._assignable_roles()
        if command.role not in allowed:
            raise AuthorizationError("Only a Super Admin can manage administrator access.")
        if user_id == self.actor_id:
            raise AuthorizationError("Ask another Super Admin to change your account access.")
        user = self.users.get(user_id, for_update=True) if user_id else None
        if user_id and user is None:
            raise EntityNotFoundError("Team member was not found.")
        if user is not None:
            assignments = list(
                self.session.scalars(
                    select(UserRole).where(
                        UserRole.company_id == self.company_id,
                        UserRole.user_id == user.id,
                        UserRole.deleted_at.is_(None),
                    )
                )
            )
            if any(item.branch_id is not None for item in assignments):
                raise ValidationError(
                    "Branch-specific access must be managed through your branch administrator."
                )
            target_roles = set(self.users.authorization_context(user.id, branch_id=None).role_names)
            actor_roles = set(self.users.authorization_context(actor.id, branch_id=None).role_names)
            if target_roles & _ADMIN_ROLES and not actor_roles & _TOP_ROLES:
                raise AuthorizationError("Only a Super Admin can change administrator accounts.")
        if (
            not command.username.strip()
            or not command.full_name.strip()
            or "@" not in command.email
        ):
            raise ValidationError("A username, full name and valid email are required.")
        if (user is None and not command.password) or (
            command.password is not None and not 12 <= len(command.password) <= 1024
        ):
            raise ValidationError("Use a password between 12 and 1024 characters.")
        if command.pin is not None and (
            not command.pin.isascii() or not command.pin.isdigit() or not 4 <= len(command.pin) <= 6
        ):
            raise ValidationError("Counter PIN must contain 4 to 6 digits.")
        role = self._role(command.role)
        created = user is None
        if user is None:
            user = User(
                company_id=self.company_id,
                username=command.username.strip(),
                email=command.email.strip().lower(),
                full_name=command.full_name.strip(),
                password_hash=hash_password(command.password or ""),
                created_by=self.actor_id,
            )
            self.session.add(user)
        else:
            user.username = command.username.strip()
            user.email = command.email.strip().lower()
            user.full_name = command.full_name.strip()
            user.session_version += 1
            user.row_version += 1
            if command.password:
                user.password_hash = hash_password(command.password)
                user.failed_login_attempts = 0
                user.locked_until = None
        user.is_active = command.is_active
        user.updated_by = self.actor_id
        if command.pin:
            user.pin_hash = hash_pin(command.pin)
        try:
            self.session.flush()
            self.session.execute(
                delete(UserRole).where(
                    UserRole.company_id == self.company_id, UserRole.user_id == user.id
                )
            )
            self.session.add(UserRole(company_id=self.company_id, user_id=user.id, role_id=role.id))
            record_audit_event(
                self.session,
                company_id=self.company_id,
                user_id=self.actor_id,
                action="TEAM_MEMBER_CREATED" if created else "TEAM_ACCESS_CHANGED",
                entity_type="User",
                entity_id=user.id,
                new_values={"role": command.role, "is_active": user.is_active},
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            structlog.get_logger(__name__).warning(
                "team_identity_conflict", company_id=self.company_id, actor_id=self.actor_id
            )
            raise ConflictError("That username or email is already used by a team member.") from exc
        return self._member(user)

    def _assignable_roles(self) -> list[str]:
        authorization = self.users.authorization_context(self.actor_id, branch_id=None)
        names = set(authorization.role_names)
        if "user.manage" not in authorization.permissions or not names & _ADMIN_ROLES:
            raise AuthorizationError("Company administrator access is required.")
        return [
            role.name
            for role in STANDARD_ROLES
            if role.name != "OWNER"
            and (names & _TOP_ROLES or role.name not in _ADMIN_ROLES)
            and role.permissions <= authorization.permissions
        ]

    def _role(self, name: str) -> Role:
        role = self.session.scalar(
            select(Role).where(
                Role.company_id == self.company_id, Role.name == name, Role.deleted_at.is_(None)
            )
        )
        if role is not None:
            permissions = set(
                self.session.scalars(
                    select(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .where(
                        RolePermission.company_id == self.company_id,
                        RolePermission.role_id == role.id,
                        RolePermission.deleted_at.is_(None),
                        Permission.deleted_at.is_(None),
                    )
                )
            )
            actor = self.users.authorization_context(self.actor_id, branch_id=None)
            definition = next(item for item in STANDARD_ROLES if item.name == name)
            if (
                not permissions <= definition.permissions
                or not permissions <= actor.permissions
                or role.max_discount_percent > actor.max_discount_percent
            ):
                raise AuthorizationError("This role exceeds your grantable permissions.")
            return role
        definition = next(item for item in STANDARD_ROLES if item.name == name)
        role = Role(
            company_id=self.company_id,
            name=name,
            description=definition.description,
            is_system=True,
            max_discount_percent=definition.max_discount_percent,
        )
        self.session.add(role)
        self.session.flush()
        permission_ids = self.session.scalars(
            select(Permission.id).where(
                Permission.code.in_(definition.permissions), Permission.deleted_at.is_(None)
            )
        )
        self.session.add_all(
            [
                RolePermission(company_id=self.company_id, role_id=role.id, permission_id=value)
                for value in permission_ids
            ]
        )
        return role

    def _member(self, user: User) -> TeamMember:
        return TeamMember(
            user.id,
            user.username,
            user.email,
            user.full_name,
            self.users.authorization_context(user.id, branch_id=None).role_names,
            user.is_active,
            user.mfa_enabled,
        )
