"""Bulk catalogue onboarding, approved price changes, and safe product images."""

from __future__ import annotations

import csv
import io
import logging
import warnings
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vglpos.domain.models import Category, Product, ProductPriceHistory, TaxRate
from vglpos.security.override_service import OverrideApprovalService
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError
from vglpos.utils.money import ZERO, money, qty, to_decimal

logger = logging.getLogger(__name__)

_REQUIRED_IMPORT_COLUMNS = frozenset(
    {"sku", "name", "tax_rate_id", "cost_price", "selling_price", "mrp"}
)
_MAX_IMPORT_BYTES = 10 * 1024 * 1024
_MAX_IMPORT_ROWS = 5000
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProductImportRow:
    """Describe validation for one spreadsheet row without mutating the catalogue."""

    row_number: int
    sku: str
    valid: bool
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProductImportPreview:
    """Summarize a bounded import and retain every row-level validation message."""

    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: tuple[ProductImportRow, ...]


@dataclass(frozen=True, slots=True)
class BulkPriceUpdateCommand:
    """Carry one manager-approved percentage price change."""

    company_id: int
    actor_user_id: int
    percentage: object
    approver_user_id: int
    approval_pin: str
    reason: str
    category_id: int | None = None


@dataclass(frozen=True, slots=True)
class BulkPriceUpdateResult:
    """Report the exact scope of an approved catalogue price mutation."""

    updated_count: int
    percentage: Decimal
    category_id: int | None


class CatalogOperationsService:
    """Own high-volume catalogue changes that need validation or approval."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def preview_import(self, filename: str, content: bytes) -> ProductImportPreview:
        """Validate CSV or XLSX rows completely without flushing catalogue state."""
        _, preview = self._validate_import(filename, content)
        return preview

    def commit_import(self, filename: str, content: bytes, *, user_id: int) -> tuple[Product, ...]:
        """Insert a previously valid file atomically so partial onboarding cannot occur."""
        if not user_id:
            raise ValidationError("Authenticated user is required.")
        normalized_rows, preview = self._validate_import(filename, content)
        if preview.invalid_rows:
            raise ValidationError("Product import contains invalid rows; run the dry-run preview.")
        products = tuple(
            Product(
                company_id=self.company_id,
                created_by=user_id,
                on_hand=Decimal("0.000"),
                reserved_quantity=Decimal("0.000"),
                **values,
            )
            for values in normalized_rows
        )
        try:
            self.session.add_all(products)
            self.session.commit()
            for product in products:
                self.session.refresh(product)
            return products
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Product import conflicts with current catalogue state.") from exc

    def error_report(self, filename: str, content: bytes) -> bytes:
        """Return a downloadable CSV containing every invalid source-row message."""
        preview = self.preview_import(filename, content)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(("row_number", "sku", "errors"))
        for row in preview.rows:
            if not row.valid:
                writer.writerow((row.row_number, row.sku, " | ".join(row.errors)))
        return output.getvalue().encode("utf-8-sig")

    def bulk_price_update(self, cmd: BulkPriceUpdateCommand) -> BulkPriceUpdateResult:
        """Apply one approved percentage to selling price and MRP with full history."""
        if cmd.company_id != self.company_id or not cmd.actor_user_id:
            raise ValidationError("Authenticated company and user are required.")
        try:
            percentage = to_decimal(cmd.percentage).quantize(Decimal("0.01"))
        except ValueError as exc:
            raise ValidationError("Bulk price percentage must be numeric.") from exc
        if percentage <= Decimal("-100.00") or percentage > Decimal("1000.00"):
            raise ValidationError("Bulk price percentage must be above -100 and at most 1000.")
        if cmd.category_id is not None:
            category = self.session.scalar(
                select(Category.id).where(
                    Category.id == cmd.category_id,
                    Category.company_id == self.company_id,
                    Category.deleted_at.is_(None),
                )
            )
            if category is None:
                raise EntityNotFoundError("Category was not found.")
        OverrideApprovalService(self.session).approve_bulk_price_update(
            company_id=self.company_id,
            actor_user_id=cmd.actor_user_id,
            category_id=cmd.category_id,
            percentage=percentage,
            approval_pin=cmd.approval_pin,
            approver_user_id=cmd.approver_user_id,
            reason=cmd.reason,
        )
        statement = (
            select(Product)
            .where(
                Product.company_id == self.company_id,
                Product.is_active.is_(True),
                Product.deleted_at.is_(None),
            )
            .order_by(Product.id)
            .with_for_update()
        )
        if cmd.category_id is not None:
            statement = statement.where(Product.category_id == cmd.category_id)
        products = tuple(self.session.scalars(statement))
        factor = (Decimal("100.00") + percentage) / Decimal("100.00")
        for product in products:
            old_selling = money(product.selling_price)
            old_mrp = money(product.mrp)
            new_selling = money(old_selling * factor)
            new_mrp = max(new_selling, money(old_mrp * factor))
            product.selling_price = new_selling
            product.mrp = new_mrp
            product.updated_by = cmd.actor_user_id
            product.row_version += 1
            self.session.add(
                ProductPriceHistory(
                    company_id=self.company_id,
                    product_id=product.id,
                    old_selling_price=old_selling,
                    new_selling_price=new_selling,
                    old_mrp=old_mrp,
                    new_mrp=new_mrp,
                    changed_by=cmd.actor_user_id,
                    created_by=cmd.actor_user_id,
                )
            )
        try:
            self.session.commit()
            return BulkPriceUpdateResult(len(products), percentage, cmd.category_id)
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Bulk price update conflicted with catalogue state.") from exc

    def store_product_image(
        self,
        product_id: int,
        *,
        user_id: int,
        content: bytes,
        storage_root: Path,
    ) -> Product:
        """Decode, resize, and re-encode an image so user bytes are never served directly."""
        if not user_id:
            raise ValidationError("Authenticated user is required.")
        if not content or len(content) > _MAX_IMAGE_BYTES:
            raise ValidationError("Product image must be between 1 byte and 5 MiB.")
        product = self.session.scalar(
            select(Product)
            .where(
                Product.id == product_id,
                Product.company_id == self.company_id,
                Product.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if product is None:
            raise EntityNotFoundError("Product was not found.")
        root = storage_root.resolve()
        directory = root / f"company-{self.company_id}"
        directory.mkdir(parents=True, exist_ok=True)
        destination = (directory / f"product-{product.id}-{uuid4().hex}.webp").resolve()
        if not destination.is_relative_to(root):
            raise ValidationError("Product image destination is invalid.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as source:
                    source.verify()
                with Image.open(io.BytesIO(content)) as source:
                    image = ImageOps.exif_transpose(source)
                    image.thumbnail((800, 800), Image.Resampling.LANCZOS)
                    normalized = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                    normalized.save(destination, format="WEBP", quality=85, method=6)
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            UnidentifiedImageError,
            OSError,
        ) as exc:
            logger.warning(
                "Rejected unsafe product image",
                extra={"company_id": self.company_id, "product_id": product_id},
            )
            raise ValidationError("Product image is invalid or unsafe.") from exc
        previous = product.image_path
        product.image_path = destination.relative_to(root).as_posix()
        product.updated_by = user_id
        product.row_version += 1
        try:
            self.session.commit()
            self.session.refresh(product)
        except IntegrityError as exc:
            self.session.rollback()
            destination.unlink(missing_ok=True)
            raise ConflictError("Product image update conflicted with catalogue state.") from exc
        if previous:
            old_path = (root / previous).resolve()
            if old_path.is_relative_to(root):
                old_path.unlink(missing_ok=True)
        return product

    def product_image_path(self, product_id: int, *, storage_root: Path) -> Path:
        """Resolve only a tenant-owned stored image contained by the configured root."""
        image_path = self.session.scalar(
            select(Product.image_path).where(
                Product.id == product_id,
                Product.company_id == self.company_id,
                Product.deleted_at.is_(None),
            )
        )
        if image_path is None:
            raise EntityNotFoundError("Product image was not found.")
        root = storage_root.resolve()
        resolved = (root / image_path).resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise EntityNotFoundError("Product image was not found.")
        return resolved

    def _validate_import(
        self, filename: str, content: bytes
    ) -> tuple[tuple[dict[str, object], ...], ProductImportPreview]:
        if not content or len(content) > _MAX_IMPORT_BYTES:
            raise ValidationError("Import file must be between 1 byte and 10 MiB.")
        rows = self._read_rows(filename, content)
        if len(rows) > _MAX_IMPORT_ROWS:
            raise ValidationError(f"Product import cannot exceed {_MAX_IMPORT_ROWS} rows.")
        if not rows:
            raise ValidationError("Product import contains no data rows.")
        existing_skus = set(
            self.session.scalars(
                select(Product.sku).where(
                    Product.company_id == self.company_id,
                    Product.deleted_at.is_(None),
                )
            )
        )
        existing_barcodes = {
            barcode
            for barcode in self.session.scalars(
                select(Product.barcode).where(
                    Product.company_id == self.company_id,
                    Product.barcode.is_not(None),
                    Product.deleted_at.is_(None),
                )
            )
            if barcode is not None
        }
        tax_rate_ids = set(
            self.session.scalars(
                select(TaxRate.id).where(
                    TaxRate.company_id == self.company_id,
                    TaxRate.deleted_at.is_(None),
                )
            )
        )
        category_ids = set(
            self.session.scalars(
                select(Category.id).where(
                    Category.company_id == self.company_id,
                    Category.deleted_at.is_(None),
                )
            )
        )
        seen_skus: set[str] = set()
        seen_barcodes: set[str] = set()
        normalized_rows: list[dict[str, object]] = []
        results: list[ProductImportRow] = []
        for row_number, row in enumerate(rows, start=2):
            errors: list[str] = []
            sku = row.get("sku", "").strip()
            name = row.get("name", "").strip()
            if not sku:
                errors.append("sku is required")
            elif len(sku) > 100:
                errors.append("sku exceeds 100 characters")
            elif sku in existing_skus or sku in seen_skus:
                errors.append("sku already exists or is duplicated in the file")
            if not name:
                errors.append("name is required")
            elif len(name) > 255:
                errors.append("name exceeds 255 characters")
            tax_rate_id = self._integer_field(row, "tax_rate_id", errors, required=True)
            if tax_rate_id is not None and tax_rate_id not in tax_rate_ids:
                errors.append("tax_rate_id was not found")
            category_id = self._integer_field(row, "category_id", errors, required=False)
            if category_id is not None and category_id not in category_ids:
                errors.append("category_id was not found")
            prices: dict[str, Decimal] = {}
            for field in ("cost_price", "selling_price", "mrp"):
                try:
                    prices[field] = money(row.get(field, ""))
                except ValueError:
                    errors.append(f"{field} must be a valid amount")
            if len(prices) == 3 and (
                prices["cost_price"] < ZERO
                or prices["selling_price"] < ZERO
                or prices["mrp"] < prices["selling_price"]
            ):
                errors.append("prices require non-negative cost/selling and MRP >= selling")
            barcode = row.get("barcode", "").strip() or None
            if barcode is not None:
                if len(barcode) > 64:
                    errors.append("barcode exceeds 64 characters")
                elif barcode in existing_barcodes or barcode in seen_barcodes:
                    errors.append("barcode already exists or is duplicated in the file")
            uom = row.get("uom", "UNIT").strip().upper() or "UNIT"
            if len(uom) > 20:
                errors.append("uom exceeds 20 characters")
            try:
                low_stock = qty(row.get("low_stock_threshold", "5.000") or "5.000")
                if low_stock < ZERO:
                    errors.append("low_stock_threshold cannot be negative")
            except ValueError:
                low_stock = Decimal("5.000")
                errors.append("low_stock_threshold must be numeric")
            boolean_values: dict[str, bool] = {}
            for field, default in (
                ("is_tax_inclusive", False),
                ("is_inventory_tracked", True),
                ("is_weighed", False),
                ("allow_negative_stock", False),
                ("is_active", True),
            ):
                try:
                    boolean_values[field] = self._boolean_field(row, field, default=default)
                except ValidationError as exc:
                    errors.append(exc.detail)
            results.append(ProductImportRow(row_number, sku, not errors, tuple(errors)))
            if errors:
                continue
            assert tax_rate_id is not None
            seen_skus.add(sku)
            if barcode is not None:
                seen_barcodes.add(barcode)
            normalized_rows.append(
                {
                    "sku": sku,
                    "name": name,
                    "name_en": row.get("name_en", "").strip() or name,
                    "name_ta": row.get("name_ta", "").strip() or None,
                    "category_id": category_id,
                    "tax_rate_id": tax_rate_id,
                    "barcode": barcode,
                    "uom": uom,
                    "cost_price": prices["cost_price"],
                    "selling_price": prices["selling_price"],
                    "mrp": prices["mrp"],
                    "is_tax_inclusive": boolean_values["is_tax_inclusive"],
                    "is_inventory_tracked": boolean_values["is_inventory_tracked"],
                    "is_weighed": boolean_values["is_weighed"],
                    "low_stock_threshold": low_stock,
                    "allow_negative_stock": boolean_values["allow_negative_stock"],
                    "is_active": boolean_values["is_active"],
                }
            )
        valid = sum(1 for row in results if row.valid)
        return tuple(normalized_rows), ProductImportPreview(
            total_rows=len(results),
            valid_rows=valid,
            invalid_rows=len(results) - valid,
            rows=tuple(results),
        )

    @staticmethod
    def _integer_field(
        row: dict[str, str], field: str, errors: list[str], *, required: bool
    ) -> int | None:
        value = row.get(field, "").strip()
        if not value:
            if required:
                errors.append(f"{field} is required")
            return None
        try:
            parsed = int(value)
        except ValueError:
            errors.append(f"{field} must be an integer")
            return None
        if parsed <= 0:
            errors.append(f"{field} must be positive")
            return None
        return parsed

    @staticmethod
    def _boolean_field(row: dict[str, str], field: str, *, default: bool = False) -> bool:
        value = row.get(field, "").strip().lower()
        if not value:
            return default
        if value in {"1", "true", "yes", "y"}:
            return True
        if value in {"0", "false", "no", "n"}:
            return False
        raise ValidationError(f"{field} must be true/false, yes/no, or 1/0.")

    @staticmethod
    def _read_rows(filename: str, content: bytes) -> tuple[dict[str, str], ...]:
        suffix = Path(filename).suffix.lower()
        if suffix == ".csv":
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValidationError("CSV import must use UTF-8 encoding.") from exc
            reader = csv.DictReader(io.StringIO(text))
            if reader.fieldnames is None:
                raise ValidationError("Import file has no header row.")
            headers = [CatalogOperationsService._header(field) for field in reader.fieldnames]
            CatalogOperationsService._validate_headers(headers)
            return tuple(
                {
                    headers[index]: str(value or "")
                    for index, value in enumerate(raw.values())
                    if index < len(headers)
                }
                for raw in reader
                if any(str(value or "").strip() for value in raw.values())
            )
        if suffix != ".xlsx":
            raise ValidationError("Product import supports only .csv and .xlsx files.")
        return CatalogOperationsService._read_xlsx(content)

    @staticmethod
    def _read_xlsx(content: bytes) -> tuple[dict[str, str], ...]:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                shared: list[str] = []
                if "xl/sharedStrings.xml" in archive.namelist():
                    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                    shared = ["".join(node.itertext()) for node in root.findall("{*}si")]
                sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise ValidationError("XLSX import is malformed or has no first worksheet.") from exc
        matrix: list[list[str]] = []
        for row_node in sheet.findall(".//{*}sheetData/{*}row"):
            values: dict[int, str] = {}
            for cell in row_node.findall("{*}c"):
                reference = cell.attrib.get("r", "A1")
                column = CatalogOperationsService._column_index(reference)
                cell_type = cell.attrib.get("t")
                value_node = cell.find("{*}v")
                if cell_type == "inlineStr":
                    inline = cell.find("{*}is")
                    value = "" if inline is None else "".join(inline.itertext())
                elif value_node is None:
                    value = ""
                elif cell_type == "s":
                    try:
                        value = shared[int(value_node.text or "0")]
                    except (IndexError, ValueError) as exc:
                        raise ValidationError("XLSX shared-string table is invalid.") from exc
                else:
                    value = value_node.text or ""
                values[column] = value
            if values:
                matrix.append([values.get(index, "") for index in range(max(values) + 1)])
        if not matrix:
            raise ValidationError("Import file has no header row.")
        headers = [CatalogOperationsService._header(value) for value in matrix[0]]
        CatalogOperationsService._validate_headers(headers)
        return tuple(
            {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
            for row in matrix[1:]
            if any(value.strip() for value in row)
        )

    @staticmethod
    def _header(value: str) -> str:
        return "_".join(value.strip().lower().split())

    @staticmethod
    def _validate_headers(headers: list[str]) -> None:
        missing = sorted(_REQUIRED_IMPORT_COLUMNS - set(headers))
        if missing:
            raise ValidationError(f"Import file is missing required columns: {', '.join(missing)}.")
        if len(headers) != len(set(headers)):
            raise ValidationError("Import file contains duplicate column names.")

    @staticmethod
    def _column_index(reference: str) -> int:
        letters = "".join(character for character in reference if character.isalpha()).upper()
        if not letters:
            return 0
        result = 0
        for character in letters:
            result = result * 26 + ord(character) - ord("A") + 1
        return result - 1
