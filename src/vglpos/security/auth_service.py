"""Tenant-resolved authentication and progressive credential lockout."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from vglpos.domain.models import User
from vglpos.repositories.identity import (
    AuthorizationContext,
    CompanyLoginRepository,
    UserRepository,
)
from vglpos.security.audit import record_audit_event, set_audit_context
from vglpos.security.mfa import generate_totp_secret, provisioning_uri, verify_totp
from vglpos.security.password import (
    hash_password,
    hash_pin,
    needs_rehash,
    pin_needs_rehash,
    verify_password,
    verify_pin,
)
from vglpos.security.tokens import IssuedTokens, TokenService
from vglpos.services.exceptions import AuthenticationError, AuthorizationError, ValidationError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_GENERIC_FAILURE = "Invalid company code, username, or credential."
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))
_DUMMY_PIN_HASH = hash_pin("000000")


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    user_id: int
    company_id: int
    branch_id: int | None
    terminal_id: int | None
    full_name: str
    authorization: AuthorizationContext
    tokens: IssuedTokens


@dataclass(frozen=True, slots=True)
class UserProfile:
    user_id: int
    company_id: int
    username: str
    email: str
    full_name: str
    branch_id: int | None
    terminal_id: int | None
    role_names: tuple[str, ...]
    permissions: frozenset[str]
    max_discount_percent: Decimal
    mfa_enabled: bool


class AuthService:
    """Authenticate only after resolving an opaque company login code."""

    def __init__(
        self,
        session: Session,
        *,
        token_service: TokenService | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.token_service = token_service or TokenService()
        self._now = now or (lambda: datetime.now(UTC))

    def authenticate(
        self,
        company_code: str,
        username: str,
        password: str,
        *,
        branch_id: int | None = None,
        terminal_id: int | None = None,
        mfa_code: str | None = None,
        login_role: Literal["staff", "admin", "super_admin"] | None = None,
    ) -> AuthenticationResult:
        """Issue tokens without revealing which tenant or credential failed."""
        company = CompanyLoginRepository(self.session).find_by_login_code(company_code)
        user = None
        if company is not None:
            user = UserRepository(self.session, company.id).find_by_username(username.strip())
        password_matches = verify_password(
            user.password_hash if user is not None else _DUMMY_PASSWORD_HASH,
            password,
        )
        if user is None or not user.is_active or not password_matches:
            if user is not None and user.is_active:
                self._record_failure(user, method="PASSWORD")
            else:
                logger.warning("login_failure_unknown_identity")
            raise AuthenticationError(_GENERIC_FAILURE)
        if self._is_locked(user):
            self._record_locked_failure(user, method="PASSWORD")
            raise AuthenticationError(_GENERIC_FAILURE)
        if user.mfa_enabled and (
            user.mfa_secret is None
            or mfa_code is None
            or not verify_totp(user.mfa_secret, mfa_code)
        ):
            self._record_failure(user, method="MFA")
            raise AuthenticationError(_GENERIC_FAILURE)
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        return self._complete_success(
            user,
            branch_id=branch_id,
            terminal_id=terminal_id,
            method="PASSWORD",
            login_role=login_role,
        )

    def authenticate_pin(
        self,
        company_code: str,
        user_id: int,
        pin: str,
        *,
        branch_id: int | None = None,
        terminal_id: int | None = None,
    ) -> AuthenticationResult:
        """Resume a counter session through the same lockout and audit path."""
        company = CompanyLoginRepository(self.session).find_by_login_code(company_code)
        user = None
        if company is not None:
            user = UserRepository(self.session, company.id).get(user_id)
        pin_matches = verify_pin(
            user.pin_hash if user is not None and user.pin_hash is not None else _DUMMY_PIN_HASH,
            pin,
        )
        if user is None or not user.is_active or user.pin_hash is None or not pin_matches:
            if user is not None and user.is_active:
                self._record_failure(user, method="PIN")
            else:
                logger.warning("pin_login_failure_unknown_identity")
            raise AuthenticationError(_GENERIC_FAILURE)
        if self._is_locked(user):
            self._record_locked_failure(user, method="PIN")
            raise AuthenticationError(_GENERIC_FAILURE)
        if user.mfa_enabled:
            raise AuthenticationError("Use your password and authenticator code to sign in.")
        if pin_needs_rehash(user.pin_hash):
            user.pin_hash = hash_pin(pin)
        return self._complete_success(
            user,
            branch_id=branch_id,
            terminal_id=terminal_id,
            method="PIN",
        )

    def refresh(
        self,
        *,
        company_id: int,
        user_id: int,
        branch_id: int | None,
        terminal_id: int | None,
    ) -> AuthenticationResult:
        """Issue fresh claims from current roles rather than copying stale permissions."""
        repository = UserRepository(self.session, company_id)
        user = repository.get(user_id)
        if user is None or not user.is_active or self._is_locked(user):
            raise AuthenticationError("The account is unavailable.")
        branch_id, terminal_id = self._validate_context(
            repository, branch_id=branch_id, terminal_id=terminal_id
        )
        authorization = repository.authorization_context(user.id, branch_id=branch_id)
        tokens = self.token_service.issue(
            user_id=user.id,
            company_id=company_id,
            branch_id=branch_id,
            terminal_id=terminal_id,
            authorization=authorization,
            session_version=user.session_version,
        )
        return AuthenticationResult(
            user_id=user.id,
            company_id=company_id,
            branch_id=branch_id,
            terminal_id=terminal_id,
            full_name=user.full_name,
            authorization=authorization,
            tokens=tokens,
        )

    def record_logout(self, *, company_id: int, user_id: int) -> None:
        """Retain a durable logout event in the same database transaction."""
        record_audit_event(
            self.session,
            company_id=company_id,
            user_id=user_id,
            action="LOGOUT",
            entity_type="User",
            entity_id=user_id,
        )
        self.session.commit()

    def profile(
        self,
        *,
        company_id: int,
        user_id: int,
        branch_id: int | None,
        terminal_id: int | None,
    ) -> UserProfile:
        """Return only the authenticated tenant's current identity and authority."""
        repository = UserRepository(self.session, company_id)
        user = repository.get(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("The account is unavailable.")
        authorization = repository.authorization_context(user.id, branch_id=branch_id)
        return UserProfile(
            user_id=user.id,
            company_id=company_id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            branch_id=branch_id,
            terminal_id=terminal_id,
            role_names=authorization.role_names,
            permissions=authorization.permissions,
            max_discount_percent=authorization.max_discount_percent,
            mfa_enabled=user.mfa_enabled,
        )

    def confirm_password(
        self, *, company_id: int, user_id: int, password: str, mfa_code: str | None = None
    ) -> User:
        """Require a fresh credential proof before changing security-sensitive settings."""
        user = UserRepository(self.session, company_id).get(user_id, for_update=True)
        if user is None or not user.is_active or self._is_locked(user):
            raise AuthorizationError("Credential confirmation failed.")
        if not verify_password(user.password_hash, password) or (
            user.mfa_enabled and not verify_totp(user.mfa_secret or "", mfa_code or "")
        ):
            self._record_failure(user, method="SECURITY_CONFIRMATION")
            raise AuthorizationError("Credential confirmation failed.")
        return user

    def setup_mfa(self, *, company_id: int, user_id: int, issuer_name: str) -> str:
        """Persist a pending secret and return its authenticator provisioning URI."""
        user = UserRepository(self.session, company_id).get(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("The account is unavailable.")
        if user.mfa_enabled:
            raise ValidationError(
                "Authenticator protection is already enabled. "
                "Disable it with a valid code before replacing it."
            )
        authorization = UserRepository(self.session, company_id).authorization_context(
            user.id, branch_id=None
        )
        if "user.manage" not in authorization.permissions:
            raise ValidationError("MFA setup is restricted to privileged roles.")
        secret = generate_totp_secret()
        user.mfa_secret = secret
        user.mfa_enabled = False
        user.updated_by = user.id
        user.row_version += 1
        self.session.commit()
        return provisioning_uri(secret, account_name=user.email, issuer_name=issuer_name)

    def enable_mfa(self, *, company_id: int, user_id: int, code: str) -> None:
        """Enable MFA only after proving the pending authenticator is configured."""
        user = UserRepository(self.session, company_id).get(user_id)
        if (
            user is None
            or user.mfa_secret is None
            or not user.is_active
            or not verify_totp(user.mfa_secret, code)
        ):
            raise AuthorizationError("MFA verification failed.")
        user.mfa_enabled = True
        user.updated_by = user.id
        user.row_version += 1
        self.session.commit()

    def disable_mfa(self, *, company_id: int, user_id: int, code: str) -> None:
        """Require a current TOTP before removing the second factor."""
        user = UserRepository(self.session, company_id).get(user_id)
        if (
            user is None
            or user.mfa_secret is None
            or not user.mfa_enabled
            or not verify_totp(user.mfa_secret, code)
        ):
            raise AuthorizationError("MFA verification failed.")
        user.mfa_enabled = False
        user.mfa_secret = None
        user.updated_by = user.id
        user.row_version += 1
        self.session.commit()

    def verify_approval_pin(self, *, company_id: int, user_id: int, pin: str) -> User:
        """Verify an approver PIN without issuing another interactive session."""
        user = UserRepository(self.session, company_id).get(user_id)
        matches = verify_pin(
            user.pin_hash if user is not None and user.pin_hash is not None else _DUMMY_PIN_HASH,
            pin,
        )
        if (
            user is None
            or not user.is_active
            or user.pin_hash is None
            or not matches
            or self._is_locked(user)
        ):
            if user is not None and user.is_active:
                self._record_failure(user, method="APPROVAL_PIN")
            raise AuthenticationError("Manager approval failed.")
        return user

    def _complete_success(
        self,
        user: User,
        *,
        branch_id: int | None,
        terminal_id: int | None,
        method: str,
        login_role: Literal["staff", "admin", "super_admin"] | None = None,
    ) -> AuthenticationResult:
        repository = UserRepository(self.session, user.company_id)
        branch_id, terminal_id = self._validate_context(
            repository, branch_id=branch_id, terminal_id=terminal_id
        )
        authorization = repository.authorization_context(user.id, branch_id=branch_id)
        required_roles = {
            "super_admin": {"OWNER", "SUPER_ADMIN"},
            "admin": {"OWNER", "SUPER_ADMIN", "ADMIN"},
        }.get(login_role or "", set())
        if required_roles and required_roles.isdisjoint(authorization.role_names):
            logger.warning(
                "login_role_denied",
                user_id=user.id,
                company_id=user.company_id,
                login_role=login_role,
            )
            raise AuthorizationError(
                "Your account does not have access to this sign-in option. "
                "Choose your assigned role or contact your administrator."
            )
        now = self._now()
        set_audit_context(self.session, user_id=user.id)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        user.updated_by = user.id
        user.row_version += 1
        record_audit_event(
            self.session,
            company_id=user.company_id,
            user_id=user.id,
            action="LOGIN_SUCCESS",
            entity_type="User",
            entity_id=user.id,
            new_values={"method": method},
        )
        try:
            self.session.commit()
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("login_success_persistence_failed", user_id=user.id)
            raise
        tokens = self.token_service.issue(
            user_id=user.id,
            company_id=user.company_id,
            branch_id=branch_id,
            terminal_id=terminal_id,
            authorization=authorization,
            session_version=user.session_version,
        )
        return AuthenticationResult(
            user_id=user.id,
            company_id=user.company_id,
            branch_id=branch_id,
            terminal_id=terminal_id,
            full_name=user.full_name,
            authorization=authorization,
            tokens=tokens,
        )

    def _record_failure(self, user: User, *, method: str) -> None:
        set_audit_context(self.session, user_id=user.id)
        user.failed_login_attempts += 1
        if user.failed_login_attempts % 5 == 0:
            lockout_cycle = user.failed_login_attempts // 5
            lockout_minutes = min(15 * (2 ** (lockout_cycle - 1)), 1440)
            user.locked_until = self._now() + timedelta(minutes=lockout_minutes)
        user.updated_by = user.id
        user.row_version += 1
        record_audit_event(
            self.session,
            company_id=user.company_id,
            user_id=user.id,
            action="LOGIN_FAILURE",
            entity_type="User",
            entity_id=user.id,
            new_values={"method": method, "attempt": user.failed_login_attempts},
        )
        try:
            self.session.commit()
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("login_failure_persistence_failed", user_id=user.id)
            raise

    def _record_locked_failure(self, user: User, *, method: str) -> None:
        record_audit_event(
            self.session,
            company_id=user.company_id,
            user_id=user.id,
            action="LOGIN_FAILURE",
            entity_type="User",
            entity_id=user.id,
            new_values={"method": method, "locked": True},
        )
        self.session.commit()

    def _is_locked(self, user: User) -> bool:
        if user.locked_until is None:
            return False
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        return locked_until > self._now()

    @staticmethod
    def _validate_context(
        repository: UserRepository,
        *,
        branch_id: int | None,
        terminal_id: int | None,
    ) -> tuple[int | None, int | None]:
        if terminal_id is not None and branch_id is None:
            branch_id = repository.terminal_branch_id(terminal_id)
            if branch_id is None:
                raise ValidationError("Terminal was not found for this company.")
        if branch_id is not None and not repository.branch_exists(branch_id):
            raise ValidationError("Branch was not found for this company.")
        if terminal_id is not None and not repository.terminal_exists(
            terminal_id, branch_id=branch_id
        ):
            raise ValidationError("Terminal was not found for this branch.")
        return branch_id, terminal_id
