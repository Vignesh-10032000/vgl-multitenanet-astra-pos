"""Authenticated write-ahead synchronization for offline counter sales."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import Branch, Sale, Terminal
from vglpos.services.checkout_service import CheckoutCommand, CheckoutService
from vglpos.services.exceptions import CheckoutError, EntityNotFoundError, ServiceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OfflineBootstrap:
    """Provide terminal-bound facts required before the counter can work offline."""

    terminal_code: str
    supplier_state: str
    signing_key: str


@dataclass(frozen=True, slots=True)
class SignedCheckoutOperation:
    """Carry one authenticated outbox operation into the synchronization boundary."""

    uuid: UUID
    command: CheckoutCommand
    payload: dict[str, Any]
    signature: str


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Keep every operation visible even when neighboring operations succeed."""

    uuid: UUID
    status: Literal["synced", "retry", "failed"]
    sale: Sale | None = None
    error_type: str | None = None
    detail: str | None = None


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _canonical_message(operation_uuid: UUID, payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{operation_uuid}.{body}".encode()


class OfflineSyncService:
    """Verify terminal signatures and commit outbox operations independently."""

    def __init__(
        self,
        session: Session,
        *,
        company_id: int,
        branch_id: int,
        terminal_id: int,
        signing_secret: str,
    ) -> None:
        if not company_id or not branch_id or not terminal_id:
            raise ValueError("Company, branch, and terminal are required for offline sync.")
        if len(signing_secret) < 32:
            raise ValueError("Offline sync signing secret must be at least 32 characters.")
        self.session = session
        self.company_id = company_id
        self.branch_id = branch_id
        self.terminal_id = terminal_id
        self._key = hmac.new(
            signing_secret.encode(),
            f"vglpos-offline-v1:{company_id}:{branch_id}:{terminal_id}".encode(),
            hashlib.sha256,
        ).digest()

    def bootstrap(self) -> OfflineBootstrap:
        """Fail closed unless the authenticated terminal still belongs to the branch."""
        row = self.session.execute(
            select(Terminal.code, Branch.state_code)
            .join(
                Branch,
                (Branch.id == Terminal.branch_id) & (Branch.company_id == Terminal.company_id),
            )
            .where(
                Terminal.id == self.terminal_id,
                Terminal.company_id == self.company_id,
                Terminal.branch_id == self.branch_id,
                Terminal.deleted_at.is_(None),
                Terminal.is_active.is_(True),
                Branch.deleted_at.is_(None),
                Branch.is_active.is_(True),
            )
        ).one_or_none()
        if row is None:
            logger.warning(
                "Offline bootstrap rejected invalid terminal context",
                extra={
                    "company_id": self.company_id,
                    "branch_id": self.branch_id,
                    "terminal_id": self.terminal_id,
                },
            )
            raise EntityNotFoundError("Terminal was not found.")
        return OfflineBootstrap(
            terminal_code=row.code,
            supplier_state=row.state_code,
            signing_key=_base64url(self._key),
        )

    def sync_batch(
        self, operations: tuple[SignedCheckoutOperation, ...] | list[SignedCheckoutOperation]
    ) -> tuple[SyncResult, ...]:
        """Commit valid operations one-by-one so a rejected bill is never silently dropped."""
        if not 1 <= len(operations) <= 100:
            raise ValueError("Offline sync batch must contain between 1 and 100 operations.")
        results: list[SyncResult] = []
        checkout = CheckoutService(self.session)
        for operation in operations:
            if not self._signature_is_valid(operation):
                logger.warning(
                    "Offline operation signature rejected",
                    extra={
                        "company_id": self.company_id,
                        "terminal_id": self.terminal_id,
                        "offline_uuid": str(operation.uuid),
                    },
                )
                results.append(
                    SyncResult(
                        uuid=operation.uuid,
                        status="failed",
                        error_type="invalid-offline-signature",
                        detail="The offline bill signature is invalid.",
                    )
                )
                continue
            try:
                sale = checkout.checkout(operation.command)
                results.append(SyncResult(uuid=operation.uuid, status="synced", sale=sale))
            except ServiceError as exc:
                retryable = isinstance(exc, CheckoutError)
                logger.warning(
                    "Offline operation could not be committed",
                    extra={
                        "company_id": self.company_id,
                        "terminal_id": self.terminal_id,
                        "offline_uuid": str(operation.uuid),
                        "error_type": exc.error_type,
                        "retryable": retryable,
                    },
                )
                results.append(
                    SyncResult(
                        uuid=operation.uuid,
                        status="retry" if retryable else "failed",
                        error_type=exc.error_type,
                        detail=exc.detail,
                    )
                )
        return tuple(results)

    def _signature_is_valid(self, operation: SignedCheckoutOperation) -> bool:
        expected = hmac.new(
            self._key,
            _canonical_message(operation.uuid, operation.payload),
            hashlib.sha256,
        ).digest()
        try:
            padding = "=" * (-len(operation.signature) % 4)
            provided = base64.urlsafe_b64decode(f"{operation.signature}{padding}")
        except (binascii.Error, ValueError, UnicodeEncodeError):
            return False
        return hmac.compare_digest(expected, provided)
