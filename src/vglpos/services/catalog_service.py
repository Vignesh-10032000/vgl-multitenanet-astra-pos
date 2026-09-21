"""Transactional product catalogue operations for the API boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.events import ProductUpdated
from vglpos.domain.models import Category, HsnCode, Product, ProductPriceHistory, TaxRate
from vglpos.repositories.base import CursorPage
from vglpos.repositories.catalog import ProductRepository
from vglpos.services.event_dispatcher import publish_event
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError
from vglpos.utils.money import money, qty


@dataclass(frozen=True, slots=True)
class CreateProductCommand:
    company_id: int
    user_id: int
    values: dict[str, Any]


@dataclass(frozen=True, slots=True)
class UpdateProductCommand:
    company_id: int
    user_id: int
    product_id: int
    values: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProductPage:
    items: tuple[Product, ...]
    next_cursor: str | None


class CatalogService:
    """Own catalogue validation and persistence without HTTP dependencies."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id
        self.repository = ProductRepository(session, company_id)

    def list_products(
        self,
        *,
        cursor: str | None,
        limit: int,
        query: str | None = None,
        barcode: str | None = None,
    ) -> ProductPage:
        """Return a tenant-scoped catalogue page without mutating state."""
        if barcode is not None:
            product = self.repository.find_by_barcode(barcode.strip())
            return ProductPage(items=(product,) if product is not None else (), next_cursor=None)
        if query is not None:
            return ProductPage(items=self.repository.search(query, limit=limit), next_cursor=None)
        page: CursorPage[Product] = self.repository.list(cursor=cursor, limit=limit)
        return ProductPage(items=page.items, next_cursor=page.next_cursor)

    def list_categories(self) -> tuple[Category, ...]:
        """Return active tenant categories for the billing filter strip."""
        statement = (
            select(Category)
            .where(
                Category.company_id == self.company_id,
                Category.deleted_at.is_(None),
                Category.is_active.is_(True),
            )
            .order_by(Category.name, Category.id)
        )
        return tuple(self.session.scalars(statement))

    def get_product(self, product_id: int) -> Product:
        """Hide cross-tenant identifiers behind the same 404 response."""
        product = self.repository.get(product_id)
        if product is None:
            raise EntityNotFoundError("Product was not found.")
        return product

    def lookup_by_barcode(self, barcode: str) -> Product:
        """Resolve one barcode with the repository's single indexed statement."""
        product = self.repository.find_by_barcode(barcode.strip())
        if product is None:
            raise EntityNotFoundError("Product was not found.")
        return product

    def create_product(self, cmd: CreateProductCommand) -> Product:
        """Validate references and commit one new zero-stock catalogue item."""
        if cmd.company_id != self.company_id or not cmd.user_id:
            raise ValidationError("Authenticated company and user are required.")
        values = dict(cmd.values)
        values["sku"] = str(values["sku"]).strip()
        values["name"] = str(values["name"]).strip()
        values["name_en"] = str(values.get("name_en") or values["name"]).strip()
        if values.get("name_ta") is not None:
            values["name_ta"] = str(values["name_ta"]).strip()
        self._validate_references(values)
        self._validate_prices(values)
        if self.repository.find_by_sku(values["sku"]) is not None:
            raise ConflictError("Product SKU already exists.")
        barcode = values.get("barcode")
        if barcode and self.repository.find_by_barcode(str(barcode)) is not None:
            raise ConflictError("Product barcode already exists.")
        product = Product(
            company_id=self.company_id,
            created_by=cmd.user_id,
            on_hand=Decimal("0.000"),
            reserved_quantity=Decimal("0.000"),
            **values,
        )
        try:
            self.repository.add(product)
            self.session.commit()
            self.session.refresh(product)
            publish_event(
                ProductUpdated(
                    company_id=self.company_id,
                    product_id=product.id,
                    occurred_at=datetime.now(UTC),
                )
            )
            return product
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Product conflicts with an existing catalogue item.") from exc

    def update_product(self, cmd: UpdateProductCommand) -> Product:
        """Commit an audited catalogue mutation and append price history when required."""
        if cmd.company_id != self.company_id or not cmd.user_id:
            raise ValidationError("Authenticated company and user are required.")
        product = self.get_product(cmd.product_id)
        values = dict(cmd.values)
        for field in ("name", "name_en", "name_ta"):
            if values.get(field) is not None:
                values[field] = str(values[field]).strip()
        self._validate_references(values)
        candidate = {
            "cost_price": values.get("cost_price", product.cost_price),
            "selling_price": values.get("selling_price", product.selling_price),
            "mrp": values.get("mrp", product.mrp),
        }
        self._validate_prices(candidate)
        barcode = values.get("barcode")
        if barcode is not None:
            existing = self.repository.find_by_barcode(str(barcode))
            if existing is not None and existing.id != product.id:
                raise ConflictError("Product barcode already exists.")
        old_selling = product.selling_price
        old_mrp = product.mrp
        for field, value in values.items():
            setattr(product, field, value)
        product.updated_by = cmd.user_id
        product.row_version += 1
        if product.selling_price != old_selling or product.mrp != old_mrp:
            self.session.add(
                ProductPriceHistory(
                    company_id=self.company_id,
                    product_id=product.id,
                    old_selling_price=old_selling,
                    new_selling_price=product.selling_price,
                    old_mrp=old_mrp,
                    new_mrp=product.mrp,
                    changed_by=cmd.user_id,
                    created_by=cmd.user_id,
                )
            )
        try:
            self.session.commit()
            self.session.refresh(product)
            publish_event(
                ProductUpdated(
                    company_id=self.company_id,
                    product_id=product.id,
                    occurred_at=datetime.now(UTC),
                )
            )
            return product
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Product update conflicts with catalogue state.") from exc

    def delete_product(self, product_id: int, *, user_id: int) -> Product:
        """Soft-delete a catalogue item while retaining fiscal and ledger references."""
        if not user_id:
            raise ValidationError("Authenticated user is required.")
        try:
            product = self.repository.soft_delete(product_id, user_id=user_id)
        except LookupError as exc:
            raise EntityNotFoundError("Product was not found.") from exc
        self.session.commit()
        publish_event(
            ProductUpdated(
                company_id=self.company_id,
                product_id=product.id,
                occurred_at=datetime.now(UTC),
            )
        )
        return product

    def _validate_references(self, values: dict[str, Any]) -> None:
        tax_rate_id = values.get("tax_rate_id")
        if tax_rate_id is not None:
            rate = self.session.scalar(
                select(TaxRate.id).where(
                    TaxRate.id == tax_rate_id,
                    TaxRate.company_id == self.company_id,
                    TaxRate.deleted_at.is_(None),
                )
            )
            if rate is None:
                raise EntityNotFoundError("Tax rate was not found.")
        category_id = values.get("category_id")
        if category_id is not None:
            category = self.session.scalar(
                select(Category.id).where(
                    Category.id == category_id,
                    Category.company_id == self.company_id,
                    Category.deleted_at.is_(None),
                )
            )
            if category is None:
                raise EntityNotFoundError("Category was not found.")
        hsn_id = values.get("hsn_id")
        if hsn_id is not None:
            hsn = self.session.scalar(
                select(HsnCode.id).where(HsnCode.id == hsn_id, HsnCode.deleted_at.is_(None))
            )
            if hsn is None:
                raise EntityNotFoundError("HSN code was not found.")

    @staticmethod
    def _validate_prices(values: dict[str, Any]) -> None:
        try:
            cost_price = money(values["cost_price"])
            selling_price = money(values["selling_price"])
            mrp = money(values["mrp"])
            if "low_stock_threshold" in values:
                values["low_stock_threshold"] = qty(values["low_stock_threshold"])
        except (KeyError, ValueError) as exc:
            raise ValidationError("Product prices are invalid.") from exc
        if cost_price < 0 or selling_price < 0 or mrp < selling_price:
            raise ValidationError("MRP must cover the non-negative selling and cost prices.")
        values["cost_price"] = cost_price
        values["selling_price"] = selling_price
        values["mrp"] = mrp
