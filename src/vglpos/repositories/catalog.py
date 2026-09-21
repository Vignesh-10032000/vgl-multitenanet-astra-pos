"""Catalogue repositories with indexed barcode and trigram search paths."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select

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
        primary_id = (
            select(Product.id)
            .where(
                Product.company_id == self.company_id,
                Product.deleted_at.is_(None),
                Product.barcode == barcode,
            )
            .limit(1)
            .scalar_subquery()
        )
        alternate_id = (
            select(ProductBarcode.product_id)
            .where(
                ProductBarcode.company_id == self.company_id,
                ProductBarcode.deleted_at.is_(None),
                ProductBarcode.barcode == barcode,
            )
            .limit(1)
            .scalar_subquery()
        )
        statement = self._base_query().where(Product.id == func.coalesce(primary_id, alternate_id))
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
                func.similarity(func.coalesce(Product.name_en, ""), term),
                func.similarity(func.coalesce(Product.name_ta, ""), term),
                func.similarity(Product.sku, term),
            )
            statement = statement.where(
                or_(
                    Product.name.op("%")(term),
                    Product.name_en.op("%")(term),
                    Product.name_ta.op("%")(term),
                    Product.sku.op("%")(term),
                )
            ).order_by(rank.desc(), Product.id)
        else:
            pattern = f"%{term}%"
            statement = statement.where(
                or_(
                    Product.name.ilike(pattern),
                    Product.name_en.ilike(pattern),
                    Product.name_ta.ilike(pattern),
                    Product.sku.ilike(pattern),
                )
            ).order_by(Product.name, Product.id)
        return tuple(self.session.scalars(statement.limit(limit)))

    def catalog_changes(
        self, *, since: datetime | None, through: datetime, limit: int
    ) -> tuple[tuple[Product, ...], bool]:
        """Return live rows and tombstones changed inside one stable sync window."""
        if limit < 1 or limit > 50000:
            raise ValueError("limit must be between 1 and 50000.")
        statement = select(Product).where(
            Product.company_id == self.company_id,
            Product.updated_at <= through,
        )
        if since is not None:
            statement = statement.where(Product.updated_at > since)
        rows = list(
            self.session.scalars(
                statement.order_by(Product.updated_at, Product.id).limit(limit + 1)
            )
        )
        return tuple(rows[:limit]), len(rows) > limit
