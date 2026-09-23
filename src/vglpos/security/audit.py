"""Append-only automatic and explicit security audit recording."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, cast

import structlog
from flask import g, has_request_context, request
from sqlalchemy import Connection, Table, event, func, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.state import InstanceState

from vglpos.domain.models import (
    Branch,
    CashMovement,
    Category,
    CreditNote,
    CreditNoteItem,
    Customer,
    DocumentSeries,
    HeldBill,
    LoyaltyLedger,
    Product,
    ProductBarcode,
    Purchase,
    PurchaseItem,
    Role,
    RolePermission,
    Sale,
    SaleItem,
    SalePayment,
    Shift,
    StockBatch,
    StockLedger,
    Supplier,
    TaxRate,
    Terminal,
    TerminalQuickKey,
    User,
    UserRole,
)
from vglpos.domain.models.operations import AuditLog

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_REDACTED_FIELDS = frozenset({"password_hash", "pin_hash", "mfa_secret"})
_AUDITED_TYPES = (
    Branch,
    CashMovement,
    Category,
    CreditNote,
    CreditNoteItem,
    Customer,
    DocumentSeries,
    Product,
    ProductBarcode,
    Purchase,
    PurchaseItem,
    Role,
    RolePermission,
    Sale,
    SaleItem,
    SalePayment,
    Shift,
    StockBatch,
    StockLedger,
    Supplier,
    TaxRate,
    Terminal,
    User,
    UserRole,
    HeldBill,
    LoyaltyLedger,
    TerminalQuickKey,
)


def _json_value(value: object) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, (Decimal, datetime, date, Enum)):
        return str(value)
    return repr(value)


def _request_context(session: Session) -> tuple[int | None, str | None, str | None, str | None]:
    user_id = session.info.get("audit_user_id")
    ip_address = session.info.get("audit_ip_address")
    user_agent = session.info.get("audit_user_agent")
    request_id = session.info.get("audit_request_id")
    if has_request_context():
        user_id = getattr(g, "user_id", user_id)
        ip_address = request.remote_addr or ip_address
        user_agent = request.user_agent.string or user_agent
        request_id = getattr(g, "request_id", request_id)
    return (
        int(user_id) if user_id is not None else None,
        str(ip_address) if ip_address else None,
        str(user_agent) if user_agent else None,
        str(request_id) if request_id else None,
    )


def set_audit_context(
    session: Session,
    *,
    user_id: int | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    """Attach actor context when work runs outside a Flask request."""
    session.info["audit_user_id"] = user_id
    session.info["audit_ip_address"] = ip_address
    session.info["audit_user_agent"] = user_agent
    session.info["audit_request_id"] = request_id


def _next_sqlite_ids(connection: Connection, count: int) -> list[int | None]:
    if connection.dialect.name != "sqlite":
        return [None] * count
    highest = connection.scalar(select(func.coalesce(func.max(AuditLog.id), 0))) or 0
    return list(range(int(highest) + 1, int(highest) + count + 1))


def _insert_rows(connection: Connection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    for row, audit_id in zip(rows, _next_sqlite_ids(connection, len(rows)), strict=True):
        if audit_id is not None:
            row["id"] = audit_id
    connection.execute(cast(Table, AuditLog.__table__).insert(), rows)


def _changes(entity: object, *, action: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    state = cast(InstanceState[Any], inspect(entity))
    old_values: dict[str, Any] = {}
    new_values: dict[str, Any] = {}
    for attribute in state.mapper.column_attrs:
        key = attribute.key
        history = state.attrs[key].history
        if action == "UPDATE" and not history.has_changes():
            continue
        if key in _REDACTED_FIELDS:
            if action != "DELETE":
                new_values[key] = "[REDACTED]"
            if action != "INSERT":
                old_values[key] = "[REDACTED]"
            continue
        if action == "INSERT":
            new_values[key] = _json_value(getattr(entity, key))
        elif action == "DELETE":
            old_values[key] = _json_value(getattr(entity, key))
        elif history.has_changes():
            old_values[key] = _json_value(history.deleted[0] if history.deleted else None)
            new_values[key] = _json_value(
                history.added[0] if history.added else getattr(entity, key)
            )
    return old_values or None, new_values or None


@event.listens_for(Session, "before_flush")
def _protect_audit_rows(session: Session, _flush_context: object, _instances: object) -> None:
    if any(isinstance(entity, AuditLog) for entity in session.dirty | session.deleted):
        raise RuntimeError("audit_log is append-only.")


@event.listens_for(Session, "after_flush")
def _audit_after_flush(session: Session, _flush_context: object) -> None:
    user_id, ip_address, user_agent, request_id = _request_context(session)
    candidates = (
        [(entity, "INSERT") for entity in session.new]
        + [(entity, "UPDATE") for entity in session.dirty]
        + [(entity, "DELETE") for entity in session.deleted]
    )
    rows: list[dict[str, Any]] = []
    timestamp = datetime.now(UTC)
    for entity, action in candidates:
        if not isinstance(entity, _AUDITED_TYPES):
            continue
        old_values, new_values = _changes(entity, action=action)
        if action == "UPDATE" and old_values is None and new_values is None:
            continue
        company_id = getattr(entity, "company_id", None)
        entity_id = getattr(entity, "id", None)
        if not company_id or entity_id is None:
            logger.error("audit_entity_missing_identity", entity_type=type(entity).__name__)
            raise RuntimeError("Audited entities require company_id and id.")
        actor_id = user_id
        if actor_id is None:
            actor_id = getattr(entity, "updated_by", None) or getattr(entity, "created_by", None)
        rows.append(
            {
                "company_id": int(company_id),
                "user_id": int(actor_id) if actor_id is not None else None,
                "action": action,
                "entity_type": type(entity).__name__,
                "entity_id": str(entity_id),
                "old_values": old_values,
                "new_values": new_values,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "request_id": request_id,
                "created_at": timestamp,
                "updated_at": timestamp,
                "row_version": 1,
            }
        )
    _insert_rows(session.connection(), rows)


def record_audit_event(
    session: Session,
    *,
    company_id: int,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | str,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
) -> None:
    """Append a named security or business event inside the caller's transaction."""
    if not company_id or not action.strip() or not entity_type.strip() or not str(entity_id):
        raise ValueError("Company, action, entity type, and entity ID are required.")
    _, ip_address, user_agent, request_id = _request_context(session)
    timestamp = datetime.now(UTC)
    _insert_rows(
        session.connection(),
        [
            {
                "company_id": company_id,
                "user_id": user_id,
                "action": action.strip().upper(),
                "entity_type": entity_type.strip(),
                "entity_id": str(entity_id),
                "old_values": old_values,
                "new_values": new_values,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "request_id": request_id,
                "created_at": timestamp,
                "updated_at": timestamp,
                "row_version": 1,
            }
        ],
    )
