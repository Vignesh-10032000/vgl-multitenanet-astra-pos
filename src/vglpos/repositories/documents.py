"""Sale aggregate persistence queries."""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, or_, select

from vglpos.domain.models import Sale, SaleItem, SalePayment
from vglpos.repositories.base import BaseRepository, CursorPage, _decode_cursor, _encode_cursor


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

    def payments(self, sale_id: int) -> tuple[SalePayment, ...]:
        """Load tender rows through both the sale and tenant boundaries."""
        return tuple(
            self.session.scalars(
                select(SalePayment)
                .where(
                    SalePayment.company_id == self.company_id,
                    SalePayment.sale_id == sale_id,
                    SalePayment.deleted_at.is_(None),
                )
                .order_by(SalePayment.id)
            )
        )

    def list_filtered(
        self,
        *,
        cursor: str | None,
        limit: int,
        branch_id: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        cashier_id: int | None = None,
        status: str | None = None,
        customer_id: int | None = None,
    ) -> CursorPage[Sale]:
        """Apply sale filters before stable keyset pagination."""
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200.")
        statement = self._base_query()
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        if start_date is not None:
            statement = statement.where(Sale.business_date >= start_date)
        if end_date is not None:
            statement = statement.where(Sale.business_date <= end_date)
        if cashier_id is not None:
            statement = statement.where(Sale.cashier_id == cashier_id)
        if status is not None:
            statement = statement.where(Sale.sale_status == status)
        if customer_id is not None:
            statement = statement.where(Sale.customer_id == customer_id)
        if cursor is not None:
            created_at, entity_id = _decode_cursor(cursor)
            if self.session.get_bind().dialect.name == "sqlite":
                statement = statement.where(Sale.id > entity_id)
            else:
                statement = statement.where(
                    or_(
                        Sale.created_at > created_at,
                        and_(Sale.created_at == created_at, Sale.id > entity_id),
                    )
                )
        rows = list(
            self.session.scalars(statement.order_by(Sale.created_at, Sale.id).limit(limit + 1))
        )
        items = tuple(rows[:limit])
        next_cursor = None
        if len(rows) > limit and items:
            next_cursor = _encode_cursor(items[-1].created_at, items[-1].id)
        return CursorPage(items=items, next_cursor=next_cursor)
