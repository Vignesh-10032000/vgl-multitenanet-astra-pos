"""Sale aggregate persistence queries."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from vglpos.domain.models import Sale, SaleItem
from vglpos.repositories.base import BaseRepository


class SaleRepository(BaseRepository[Sale]):
    """Query immutable fiscal sales within one company."""

    model = Sale

    def find_by_offline_uuid(self, offline_uuid: str) -> Sale | None:
        """Return the original sale for an idempotent offline replay."""
        return self.session.scalar(self._base_query().where(Sale.offline_uuid == offline_uuid))

    def for_business_date(self, on_date: date, *, branch_id: int | None = None) -> tuple[Sale, ...]:
        """Return completed sales for one reporting date in invoice order."""
        statement = self._base_query().where(
            Sale.business_date == on_date,
            Sale.sale_status == "COMPLETED",
        )
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        return tuple(self.session.scalars(statement.order_by(Sale.id)))

    def items(self, sale_id: int) -> tuple[SaleItem, ...]:
        """Load sale lines with both sale and item tenant predicates."""
        statement = (
            select(SaleItem)
            .where(
                SaleItem.company_id == self.company_id,
                SaleItem.sale_id == sale_id,
                SaleItem.deleted_at.is_(None),
            )
            .order_by(SaleItem.line_number, SaleItem.id)
        )
        return tuple(self.session.scalars(statement))
