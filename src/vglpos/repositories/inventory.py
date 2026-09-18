"""Stock-ledger persistence queries."""

from __future__ import annotations

from vglpos.domain.models import StockLedger
from vglpos.repositories.base import BaseRepository


class StockRepository(BaseRepository[StockLedger]):
    """Query append-only inventory movements within one company."""

    model = StockLedger

    def for_product(
        self,
        product_id: int,
        *,
        branch_id: int | None = None,
        limit: int = 100,
    ) -> tuple[StockLedger, ...]:
        """Return the newest ledger history for one product."""
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        statement = self._base_query().where(StockLedger.product_id == product_id)
        if branch_id is not None:
            statement = statement.where(StockLedger.branch_id == branch_id)
        statement = statement.order_by(StockLedger.created_at.desc(), StockLedger.id.desc())
        return tuple(self.session.scalars(statement.limit(limit)))
