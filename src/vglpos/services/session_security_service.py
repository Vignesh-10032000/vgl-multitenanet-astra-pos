"""Persisted session revocation that survives cache resets and worker changes."""

from __future__ import annotations

import structlog
from sqlalchemy.orm import Session

from vglpos.repositories.identity import UserRepository
from vglpos.security.audit import record_audit_event
from vglpos.services.exceptions import EntityNotFoundError


class SessionSecurityService:
    """Validate the current account state for access and refresh tokens."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def is_current(self, user_id: int, version: int) -> bool:
        """Reject disabled users and every token issued before an access change."""
        current = UserRepository(self.session, self.company_id).session_is_current(user_id, version)
        if not current:
            structlog.get_logger(__name__).warning(
                "session_account_state_changed",
                company_id=self.company_id,
                user_id=user_id,
                token_version=version,
            )
        return current

    def revoke_all(self, user_id: int) -> None:
        """Expire every device's tokens while retaining an auditable account event."""
        user = UserRepository(self.session, self.company_id).get(user_id, for_update=True)
        if user is None:
            raise EntityNotFoundError("The account is unavailable.")
        user.session_version += 1
        record_audit_event(
            self.session,
            company_id=self.company_id,
            user_id=user_id,
            action="ALL_SESSIONS_REVOKED",
            entity_type="User",
            entity_id=user_id,
        )
        self.session.commit()
