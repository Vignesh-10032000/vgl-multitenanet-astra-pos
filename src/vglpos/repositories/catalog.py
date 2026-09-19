"""Catalogue repositories with indexed barcode and trigram search paths."""

from __future__ import annotations

from sqlalchemy import exists, func, or_, select

from vglpos.domain.models import Product, ProductBarcode
from vglpos.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """Query live products within one company."""

    model = Product

    def find_by_sku(self, sku: str) -> Product | None:
        """Resolve one normalized tenant SKU through its unique index."""
        return self.session.scalar(self._base_query().where(Product.sku == sku.strip()))

    def find_by_barcode(self, barcode: str, *, for_update: bool = False) -> Product | None:
        """Resolve primary or alternate barcode in one indexed database lookup."""
        alternate = exists(
            select(ProductBarcode.id).where(
                ProductBarcode.company_id == self.company_id,
                ProductBarcode.deleted_at.is_(None),
                ProductBarcode.product_id == Product.id,
                ProductBarcode.barcode == barcode,
            )
        )
        statement = self._base_query().where(or_(Product.barcode == barcode, alternate))
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def search(self, query: str, *, limit: int = 20) -> tuple[Product, ...]:
        """Use PostgreSQL trigram ranking and a deterministic SQLite test fallback."""
        term = query.strip()
        if not term:
            return ()
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100.")
        statement = self._base_query()
        dialect = self.session.get_bind().dialect.name
        if dialect == "postgresql":
            rank = func.greatest(
                func.similarity(Product.name, term),
                func.similarity(Product.sku, term),
            )
            statement = statement.where(
                or_(Product.name.op("%")(term), Product.sku.op("%")(term))
            ).order_by(rank.desc(), Product.id)
        else:
            pattern = f"%{term}%"
            statement = statement.where(
                or_(Product.name.ilike(pattern), Product.sku.ilike(pattern))
            ).order_by(Product.name, Product.id)
        return tuple(self.session.scalars(statement.limit(limit)))
