"""Tenant-safe SQLAlchemy repository primitives."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from vglpos.domain.models.base import TenantEntity


class RepositoryEntityNotFoundError(LookupError):
    """Report a missing entity without leaking another tenant's existence."""


@dataclass(frozen=True, slots=True)
class CursorPage[T: TenantEntity]:
    """Return a keyset page and the opaque cursor for the following page."""

    items: tuple[T, ...]
    next_cursor: str | None

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> T:
        return self.items[index]


def _encode_cursor(created_at: datetime, entity_id: int) -> str:
    payload = f"{created_at.isoformat()}|{entity_id}".encode("ascii")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = base64.urlsafe_b64decode(f"{cursor}{padding}").decode("ascii")
        timestamp, raw_id = payload.rsplit("|", maxsplit=1)
        created_at = datetime.fromisoformat(timestamp)
        entity_id = int(raw_id)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid pagination cursor.") from exc
    if entity_id <= 0:
        raise ValueError("Invalid pagination cursor.")
    return created_at, entity_id


class BaseRepository[T: TenantEntity]:
    """Provide company-scoped CRUD operations for one tenant entity type."""

    model: type[T]

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def _base_query(self) -> Select[tuple[T]]:
        """Build the mandatory tenant and live-row predicates for every read."""
        return select(self.model).where(
            self.model.company_id == self.company_id,
            self.model.deleted_at.is_(None),
        )

    def get(self, entity_id: int, *, for_update: bool = False) -> T | None:
        """Return one live tenant entity and optionally lock it for mutation."""
        statement = self._base_query().where(self.model.id == entity_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def get_or_raise(self, entity_id: int, *, for_update: bool = False) -> T:
        """Return one entity or raise the same not-found error across tenants."""
        entity = self.get(entity_id, for_update=for_update)
        if entity is None:
            raise RepositoryEntityNotFoundError(f"{self.model.__name__} {entity_id} was not found.")
        return entity

    def list(self, *, cursor: str | None = None, limit: int = 50) -> CursorPage[T]:
        """List entities with stable `(created_at, id)` keyset pagination."""
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200.")
        statement = self._base_query()
        if cursor is not None:
            created_at, entity_id = _decode_cursor(cursor)
            if self.session.get_bind().dialect.name == "sqlite":
                # SQLite's CURRENT_TIMESTAMP omits fractional seconds, while its
                # DateTime binder adds them back. Identity order is monotonic in
                # the supported single-file desktop database.
                statement = statement.where(self.model.id > entity_id)
            else:
                statement = statement.where(
                    or_(
                        self.model.created_at > created_at,
                        and_(
                            self.model.created_at == created_at,
                            self.model.id > entity_id,
                        ),
                    )
                )
        statement = statement.order_by(self.model.created_at, self.model.id).limit(limit + 1)
        rows = list(self.session.scalars(statement))
        has_more = len(rows) > limit
        items = tuple(rows[:limit])
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = _encode_cursor(last.created_at, last.id)
        return CursorPage(items=items, next_cursor=next_cursor)

    def add(self, entity: T) -> T:
        """Stage a tenant-owned entity and obtain its identifier without committing."""
        if entity.company_id != self.company_id:
            raise ValueError("Entity company_id does not match repository company_id.")
        self.session.add(entity)
        self.session.flush()
        return entity

    def soft_delete(self, entity_id: int, *, user_id: int | None = None) -> T:
        """Mark one tenant row deleted while leaving transaction ownership to the caller."""
        entity = self.get_or_raise(entity_id, for_update=True)
        entity.deleted_at = datetime.now(UTC)
        entity.deleted_by = user_id
        entity.row_version += 1
        self.session.flush()
        return entity

    def count(self) -> int:
        """Count only live rows owned by this repository's tenant."""
        subquery = self._base_query().subquery()
        return cast(int, self.session.scalar(select(func.count()).select_from(subquery)) or 0)

    def statement(self) -> Select[tuple[T]]:
        """Expose the scoped selectable for specialized repository composition."""
        return self._base_query()
