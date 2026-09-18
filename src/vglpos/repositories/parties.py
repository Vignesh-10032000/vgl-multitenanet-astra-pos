"""Customer persistence queries."""

from __future__ import annotations

from sqlalchemy import or_

from vglpos.domain.models import Customer
from vglpos.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    """Query live customers within one company."""

    model = Customer

    def find_by_phone(self, phone: str) -> Customer | None:
        """Find a customer using the tenant phone uniqueness index."""
        return self.session.scalar(self._base_query().where(Customer.phone == phone))

    def search(self, query: str, *, limit: int = 20) -> tuple[Customer, ...]:
        """Search customer name or phone without crossing the tenant boundary."""
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100.")
        pattern = f"%{query.strip()}%"
        statement = (
            self._base_query()
            .where(or_(Customer.name.ilike(pattern), Customer.phone.ilike(pattern)))
            .order_by(Customer.name, Customer.id)
            .limit(limit)
        )
        return tuple(self.session.scalars(statement))
