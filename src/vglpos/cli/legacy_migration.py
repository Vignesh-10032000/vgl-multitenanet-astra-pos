"""All-or-nothing migration from the prototype SQLite database."""

from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from flask.cli import with_appcontext
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import InstrumentedAttribute, Session

from vglpos.domain.enums import PaymentMethod, ReturnReason, SaleStatus, SupplyType
from vglpos.domain.models import (
    Branch,
    Category,
    Company,
    CreditNote,
    CreditNoteItem,
    Customer,
    HsnCode,
    LegacyIdMap,
    Product,
    ProductBarcode,
    Sale,
    SaleItem,
    SalePayment,
    StockLedger,
    TaxRate,
    Terminal,
    User,
)
from vglpos.domain.models.base import TenantEntity
from vglpos.extensions import db
from vglpos.services.inventory_service import InventoryService
from vglpos.services.tax_engine import TaxEngine, TaxLineInput, TaxResult
from vglpos.utils.gst import financial_year_code, state_code_from_gstin, validate_gstin
from vglpos.utils.money import ZERO, money, qty, to_decimal

IST = ZoneInfo("Asia/Kolkata")
REQUIRED_LEGACY_TABLES = frozenset(
    {
        "categories",
        "products",
        "customers",
        "sales",
        "sale_items",
        "sale_returns",
        "sale_return_items",
    }
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompanyImportConfig(_StrictModel):
    """Legal tenant facts that cannot be inferred from prototype data."""

    name: str = Field(min_length=1, max_length=255)
    legal_name: str = Field(min_length=1, max_length=255)
    login_code: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    gstin: str | None = Field(default=None, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    cin: str | None = Field(default=None, max_length=21)
    state_code: str = Field(pattern=r"^\d{2}$")
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=10)
    contact_email: str = Field(min_length=3, max_length=255)
    contact_phone: str = Field(min_length=1, max_length=20)


class BranchImportConfig(_StrictModel):
    """Physical location facts required by the target branch model."""

    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    gstin: str | None = Field(default=None, max_length=15)
    state_code: str = Field(pattern=r"^\d{2}$")
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=10)
    phone: str = Field(min_length=1, max_length=20)


class TerminalImportConfig(_StrictModel):
    """Counter identity required for every imported fiscal sale."""

    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    terminal_type: str = Field(default="COUNTER", min_length=1, max_length=50)


class SystemUserImportConfig(_StrictModel):
    """Disabled audit user credentials supplied by the operator."""

    email: str = Field(min_length=3, max_length=255)
    password_hash: str = Field(min_length=1, max_length=255)
    full_name: str = Field(default="Legacy Import", min_length=1, max_length=255)


class LegacyMigrationConfig(_StrictModel):
    """Operator-supplied facts and business-day policy for an import run."""

    company: CompanyImportConfig
    branch: BranchImportConfig
    terminal: TerminalImportConfig
    system_user: SystemUserImportConfig
    day_close_hour: int = Field(ge=0, le=23)


@dataclass(frozen=True, slots=True)
class SumCheck:
    table: str
    field: str
    source: Decimal
    target: Decimal

    @property
    def matches(self) -> bool:
        return money(self.source) == money(self.target)


@dataclass(frozen=True, slots=True)
class TaxCorrection:
    legacy_sale_id: int
    invoice_number: str
    original_taxable: Decimal
    original_cgst: Decimal
    original_sgst: Decimal
    original_igst: Decimal
    original_cess: Decimal
    original_round_off: Decimal
    original_net: Decimal
    corrected_taxable: Decimal
    corrected_cgst: Decimal
    corrected_sgst: Decimal
    corrected_igst: Decimal
    corrected_cess: Decimal
    corrected_round_off: Decimal
    corrected_net: Decimal


@dataclass(slots=True)
class MigrationReport:
    """Collect evidence needed to approve or reject one migration run."""

    legacy_database: Path
    backup_file: Path
    config_file: Path
    dry_run: bool
    apply_tax_corrections: bool
    status: str = "RUNNING"
    company_id: int | None = None
    row_counts: dict[str, tuple[int, int]] = field(default_factory=dict)
    sum_checks: list[SumCheck] = field(default_factory=list)
    business_day_shifts: int = 0
    tax_corrections: list[TaxCorrection] = field(default_factory=list)
    defaults_used: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def write(self, output_dir: Path) -> tuple[Path, Path]:
        """Persist human and accountant review artifacts outside the DB transaction."""
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / "MIGRATION_REPORT.md"
        csv_path = output_dir / "MIGRATION_TAX_CORRECTIONS.csv"
        markdown_path.write_text(self._markdown(), encoding="utf-8")
        self._write_corrections(csv_path)
        return markdown_path, csv_path

    def _markdown(self) -> str:
        rows = [
            "# Legacy Migration Report",
            "",
            f"- Status: **{self.status}**",
            f"- Mode: **{'dry-run' if self.dry_run else 'apply'}**",
            f"- Legacy database: `{self.legacy_database}`",
            f"- Backup snapshot: `{self.backup_file}`",
            f"- Configuration: `{self.config_file}`",
            f"- Apply tax corrections: `{self.apply_tax_corrections}`",
            f"- Imported company ID: `{self.company_id}`",
            f"- Business dates changed from the UTC calendar date: **{self.business_day_shifts}**",
            f"- Tax corrections detected: **{len(self.tax_corrections)}**",
            "",
            "## Row Counts",
            "",
            "| Table | Legacy | Target | Match |",
            "|---|---:|---:|:---:|",
        ]
        for table, (source, target) in sorted(self.row_counts.items()):
            rows.append(
                f"| {table} | {source} | {target} | {'yes' if source == target else 'NO'} |"
            )
        rows.extend(
            [
                "",
                "## Sum Checks",
                "",
                "| Table | Field | Legacy/Expected | Target | Match |",
                "|---|---|---:|---:|:---:|",
            ]
        )
        for check in self.sum_checks:
            rows.append(
                f"| {check.table} | {check.field} | {money(check.source)} | "
                f"{money(check.target)} | {'yes' if check.matches else 'NO'} |"
            )
        rows.extend(["", "## Documented Defaults", ""])
        rows.extend(f"- {item}" for item in self.defaults_used)
        if not self.defaults_used:
            rows.append("- None")
        rows.extend(["", "## Skipped or Unrepresented Fields", ""])
        rows.extend(f"- {item}" for item in self.skipped)
        if not self.skipped:
            rows.append("- None")
        rows.extend(["", "## Tax Corrections", ""])
        if self.tax_corrections:
            rows.append(
                "See `MIGRATION_TAX_CORRECTIONS.csv`; corrections are applied only when "
                "`--apply-tax-corrections` is present."
            )
        else:
            rows.append("No differences from TaxEngine were detected.")
        rows.append("")
        return "\n".join(rows)

    def _write_corrections(self, path: Path) -> None:
        field_names = tuple(TaxCorrection.__dataclass_fields__)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=field_names)
            writer.writeheader()
            for correction in self.tax_corrections:
                writer.writerow({name: str(getattr(correction, name)) for name in field_names})


class LegacyMigrationError(RuntimeError):
    """Abort an import while retaining its generated review artifacts."""


def _load_config(path: Path) -> LegacyMigrationConfig:
    if not path.is_file():
        raise LegacyMigrationError(f"Migration config file does not exist: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return LegacyMigrationConfig.model_validate(raw)
    except (json.JSONDecodeError, OSError, PydanticValidationError) as exc:
        raise LegacyMigrationError(f"Migration config is invalid: {exc}") from exc


def backup_legacy_database(source: Path, *, at: datetime | None = None) -> Path:
    """Consolidate the SQLite database and any WAL pages into a timestamped snapshot."""
    if not source.is_file():
        raise LegacyMigrationError(f"Legacy database does not exist: {source}")
    timestamp = (at or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
    backup = source.with_name(f"{source.stem}.backup-{timestamp}{source.suffix}")
    try:
        with (
            closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as legacy,
            closing(sqlite3.connect(backup)) as destination,
        ):
            legacy.backup(destination)
    except sqlite3.Error as exc:
        backup.unlink(missing_ok=True)
        raise LegacyMigrationError(f"Could not back up legacy database: {exc}") from exc
    return backup


def _legacy_decimal(value: object | None) -> Decimal:
    """Convert SQLite numeric values through text, never binary-float construction."""
    return to_decimal("0" if value is None else str(value))


def _legacy_money(value: object | None) -> Decimal:
    return money(_legacy_decimal(value))


def _legacy_qty(value: object | None) -> Decimal:
    return qty(_legacy_decimal(value))


def _utc_datetime(value: object | None) -> datetime:
    if value is None or not str(value).strip():
        raise LegacyMigrationError("A required legacy timestamp is missing.")
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise LegacyMigrationError(f"Invalid legacy timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _business_date(timestamp: datetime, day_close_hour: int) -> date:
    local = timestamp.astimezone(IST)
    business_day = local.date()
    if local.hour < day_close_hour:
        business_day -= timedelta(days=1)
    return business_day


def _rows(connection: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(connection.execute(f'SELECT * FROM "{table}" ORDER BY id'))


def _source_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _source_sum(connection: sqlite3.Connection, table: str, field_name: str) -> Decimal:
    values = connection.execute(f'SELECT "{field_name}" FROM "{table}"').fetchall()
    return money(sum((_legacy_money(row[0]) for row in values), ZERO))


@dataclass(frozen=True, slots=True)
class _PreparedSale:
    row: sqlite3.Row
    item_rows: tuple[sqlite3.Row, ...]
    timestamp: datetime
    business_date: date
    invoice_number: str
    calculation: TaxResult


_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "categories": frozenset({"id", "name", "icon"}),
    "products": frozenset(
        {
            "id",
            "name",
            "sku",
            "barcode",
            "price",
            "cost",
            "stock",
            "low_stock_threshold",
            "category_id",
            "gst_rate",
            "hsn_code",
            "active",
            "created_at",
        }
    ),
    "customers": frozenset({"id", "name", "email", "phone", "gstin", "points", "created_at"}),
    "sales": frozenset(
        {
            "id",
            "customer_id",
            "subtotal",
            "total_cgst",
            "total_sgst",
            "total",
            "discount",
            "amount_paid",
            "change_given",
            "payment_method",
            "notes",
            "created_at",
        }
    ),
    "sale_items": frozenset(
        {"id", "sale_id", "product_id", "quantity", "price", "gst_rate", "subtotal"}
    ),
    "sale_returns": frozenset(
        {"id", "sale_id", "refund_amount", "payment_method", "reason", "created_at"}
    ),
    "sale_return_items": frozenset(
        {"id", "sale_return_id", "product_id", "quantity", "price", "subtotal"}
    ),
}


class LegacyMigrator:
    """Move one immutable legacy snapshot into one target transaction."""

    def __init__(
        self,
        session: Session,
        source: sqlite3.Connection,
        config: LegacyMigrationConfig,
        report: MigrationReport,
        *,
        apply_tax_corrections: bool,
    ) -> None:
        self.session = session
        self.source = source
        self.config = config
        self.report = report
        self.apply_tax_corrections = apply_tax_corrections
        self.company: Company | None = None
        self.branch: Branch | None = None
        self.terminal: Terminal | None = None
        self.user: User | None = None
        self.category_ids: dict[int, int] = {}
        self.product_ids: dict[int, int] = {}
        self.customer_ids: dict[int, int] = {}
        self.sale_ids: dict[int, int] = {}
        self.sale_item_ids: dict[int, int] = {}
        self.credit_note_ids: dict[int, int] = {}
        self.tax_rates: dict[Decimal, TaxRate] = {}
        self.prepared_sales: list[_PreparedSale] = []

    @property
    def company_id(self) -> int:
        if self.company is None or self.company.id is None:
            raise LegacyMigrationError("Tenant scaffolding has not been created.")
        return self.company.id

    @property
    def branch_id(self) -> int:
        if self.branch is None or self.branch.id is None:
            raise LegacyMigrationError("Branch scaffolding has not been created.")
        return self.branch.id

    @property
    def terminal_id(self) -> int:
        if self.terminal is None or self.terminal.id is None:
            raise LegacyMigrationError("Terminal scaffolding has not been created.")
        return self.terminal.id

    @property
    def user_id(self) -> int:
        if self.user is None or self.user.id is None:
            raise LegacyMigrationError("System-user scaffolding has not been created.")
        return self.user.id

    def run(self) -> None:
        """Validate, import, and reconcile without committing the caller's transaction."""
        self._validate_source_schema()
        self._preflight_target()
        self._create_scaffolding()
        self._create_tax_rates()
        self._migrate_categories()
        self._migrate_products()
        self._migrate_customers()
        self._prepare_sales()
        if self.report.tax_corrections and not (self.report.dry_run or self.apply_tax_corrections):
            raise LegacyMigrationError(
                "Tax corrections require accountant approval; rerun with "
                "--apply-tax-corrections after reviewing MIGRATION_TAX_CORRECTIONS.csv."
            )
        self._migrate_sales()
        self._migrate_returns()
        self._verify_all_checks()

    def _validate_source_schema(self) -> None:
        tables = {
            str(row[0])
            for row in self.source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        missing_tables = sorted(REQUIRED_LEGACY_TABLES - tables)
        if missing_tables:
            raise LegacyMigrationError(
                f"Legacy database is missing required tables: {', '.join(missing_tables)}"
            )
        for table, required in _REQUIRED_COLUMNS.items():
            available = {
                str(row[1]) for row in self.source.execute(f'PRAGMA table_info("{table}")')
            }
            missing_columns = sorted(required - available)
            if missing_columns:
                raise LegacyMigrationError(
                    f"Legacy table {table} is missing columns: {', '.join(missing_columns)}"
                )

    def _preflight_target(self) -> None:
        sale_count = self.session.scalar(select(func.count()).select_from(Sale)) or 0
        if sale_count:
            raise LegacyMigrationError(
                f"Target database already contains {sale_count} sale row(s); refusing import."
            )
        self._validate_config_gstin("company", self.config.company.gstin)
        self._validate_config_gstin("branch", self.config.branch.gstin)
        if self.config.company.gstin and (
            state_code_from_gstin(self.config.company.gstin) != self.config.company.state_code
        ):
            raise LegacyMigrationError("Company GSTIN does not match its configured state code.")
        if self.config.branch.gstin and (
            state_code_from_gstin(self.config.branch.gstin) != self.config.branch.state_code
        ):
            raise LegacyMigrationError("Branch GSTIN does not match its configured state code.")

    @staticmethod
    def _validate_config_gstin(label: str, gstin: str | None) -> None:
        if gstin and not validate_gstin(gstin):
            raise LegacyMigrationError(f"Configured {label} GSTIN is invalid.")

    def _create_scaffolding(self) -> None:
        company_cfg = self.config.company
        self.company = Company(
            name=company_cfg.name,
            legal_name=company_cfg.legal_name,
            login_code=company_cfg.login_code.upper(),
            gstin=self._normalized_optional(company_cfg.gstin),
            pan=self._normalized_optional(company_cfg.pan),
            cin=self._normalized_optional(company_cfg.cin),
            state_code=company_cfg.state_code,
            address_line1=company_cfg.address_line1,
            address_line2=self._normalized_optional(company_cfg.address_line2),
            city=company_cfg.city,
            state=company_cfg.state,
            postal_code=company_cfg.postal_code,
            contact_email=company_cfg.contact_email,
            contact_phone=company_cfg.contact_phone,
        )
        self.session.add(self.company)
        self.session.flush()

        user_cfg = self.config.system_user
        self.user = User(
            company_id=self.company_id,
            username="legacy-import",
            email=user_cfg.email,
            password_hash=user_cfg.password_hash,
            full_name=user_cfg.full_name,
            is_active=False,
            is_superuser=False,
        )
        self.session.add(self.user)
        self.session.flush()

        branch_cfg = self.config.branch
        self.branch = Branch(
            company_id=self.company_id,
            code=branch_cfg.code,
            name=branch_cfg.name,
            gstin=self._normalized_optional(branch_cfg.gstin),
            state_code=branch_cfg.state_code,
            address_line1=branch_cfg.address_line1,
            address_line2=self._normalized_optional(branch_cfg.address_line2),
            city=branch_cfg.city,
            state=branch_cfg.state,
            postal_code=branch_cfg.postal_code,
            phone=branch_cfg.phone,
            is_head_office=True,
            created_by=self.user_id,
        )
        self.session.add(self.branch)
        self.session.flush()

        terminal_cfg = self.config.terminal
        self.terminal = Terminal(
            company_id=self.company_id,
            branch_id=self.branch_id,
            code=terminal_cfg.code,
            name=terminal_cfg.name,
            terminal_type=terminal_cfg.terminal_type,
            created_by=self.user_id,
        )
        self.session.add(self.terminal)
        self.session.flush()
        self.company.created_by = self.user_id
        self.user.created_by = self.user_id
        self.report.company_id = self.company_id

    def _create_tax_rates(self) -> None:
        rates = sorted({_legacy_money(row["gst_rate"]) for row in _rows(self.source, "products")})
        for rate in rates:
            if rate < ZERO or rate > Decimal("100.00"):
                raise LegacyMigrationError(f"Unsupported legacy GST rate: {rate}")
            tax_rate = TaxRate(
                company_id=self.company_id,
                name=f"Legacy GST {rate}%",
                rate=rate,
                cgst_rate=money(rate / Decimal("2")),
                sgst_rate=money(rate / Decimal("2")),
                igst_rate=rate,
                cess_rate=ZERO,
                effective_from=date(2017, 7, 1),
                created_by=self.user_id,
            )
            self.session.add(tax_rate)
            self.tax_rates[rate] = tax_rate
        self.session.flush()

    def _migrate_categories(self) -> None:
        rows = _rows(self.source, "categories")
        for row in rows:
            legacy_id = int(row["id"])
            category = Category(
                company_id=self.company_id,
                name=str(row["name"]),
                code=f"LEGACY-{legacy_id}",
                icon=self._normalized_optional(row["icon"]),
                created_by=self.user_id,
            )
            self.session.add(category)
            self.session.flush()
            self.category_ids[legacy_id] = category.id
            self._map("categories", legacy_id, "categories", category.id)
            self.report.defaults_used.append(
                f"categories[{legacy_id}].code = LEGACY-{legacy_id}; no legacy code existed."
            )
        self._count_check("categories", Category)
        self._fail_if_new_mismatch()

    def _migrate_products(self) -> None:
        rows = _rows(self.source, "products")
        inventory = InventoryService(self.session, self.company_id)
        hsn_ids: dict[str, int] = {}
        barcode_count = 0
        for row in rows:
            legacy_id = int(row["id"])
            timestamp = _utc_datetime(row["created_at"])
            hsn_id = self._hsn_id(self._normalized_optional(row["hsn_code"]), hsn_ids)
            category_id = self._mapped_optional(
                self.category_ids, row["category_id"], "category", legacy_id
            )
            rate = _legacy_money(row["gst_rate"])
            price = _legacy_money(row["price"])
            cost = _legacy_money(row["cost"])
            stock = _legacy_qty(row["stock"])
            threshold = _legacy_qty(row["low_stock_threshold"])
            if price < ZERO or cost < ZERO or stock < ZERO or threshold < ZERO:
                raise LegacyMigrationError(
                    f"products[{legacy_id}] has a negative price, cost, stock, or threshold."
                )
            product = Product(
                company_id=self.company_id,
                sku=str(row["sku"]),
                name=str(row["name"]),
                category_id=category_id,
                hsn_id=hsn_id,
                tax_rate_id=self.tax_rates[rate].id,
                barcode=self._normalized_optional(row["barcode"]),
                cost_price=cost,
                selling_price=price,
                mrp=price,
                is_tax_inclusive=True,
                low_stock_threshold=threshold,
                on_hand=qty(ZERO),
                is_active=bool(row["active"]),
                created_at=timestamp,
                created_by=self.user_id,
            )
            self.session.add(product)
            self.session.flush()
            self.product_ids[legacy_id] = product.id
            self._map("products", legacy_id, "products", product.id, at=timestamp)

            barcode = self._normalized_optional(row["barcode"])
            if barcode:
                product_barcode = ProductBarcode(
                    company_id=self.company_id,
                    product_id=product.id,
                    barcode=barcode,
                    is_primary=True,
                    created_at=timestamp,
                    created_by=self.user_id,
                )
                self.session.add(product_barcode)
                self.session.flush()
                self._map(
                    "product_barcodes",
                    legacy_id,
                    "product_barcodes",
                    product_barcode.id,
                    at=timestamp,
                )
                barcode_count += 1

            if stock == qty(ZERO):
                self.session.add(
                    StockLedger(
                        company_id=self.company_id,
                        branch_id=self.branch_id,
                        product_id=product.id,
                        txn_type="OPENING",
                        reference_id=str(legacy_id),
                        reference_type="legacy_products",
                        quantity=stock,
                        balance_after=stock,
                        unit_cost=cost,
                        notes="Legacy opening balance",
                        created_at=timestamp,
                        created_by=self.user_id,
                    )
                )
            else:
                ledger = inventory.record_movement(
                    product,
                    self.branch_id,
                    stock,
                    "OPENING",
                    "legacy_products",
                    legacy_id,
                    self.user_id,
                    unit_cost=cost,
                    notes="Legacy opening balance",
                )
                ledger.created_at = timestamp

        self.session.flush()
        self._count_check("products", Product)
        self.report.row_counts["product_barcodes"] = (
            barcode_count,
            self._target_count(ProductBarcode),
        )
        self.report.row_counts["stock_ledger (OPENING)"] = (
            len(rows),
            self._target_count(StockLedger),
        )
        self._sum_check(
            "products",
            "price",
            _source_sum(self.source, "products", "price"),
            Product.selling_price,
        )
        self._sum_check(
            "products", "cost", _source_sum(self.source, "products", "cost"), Product.cost_price
        )
        self._sum_check(
            "products", "stock", _source_sum(self.source, "products", "stock"), Product.on_hand
        )
        self._sum_check(
            "products",
            "low_stock_threshold",
            _source_sum(self.source, "products", "low_stock_threshold"),
            Product.low_stock_threshold,
        )
        source_rate_sum = _source_sum(self.source, "products", "gst_rate")
        target_rate_sum = money(
            sum(
                (self.tax_rates[_legacy_money(row["gst_rate"])].rate for row in rows),
                ZERO,
            )
        )
        self.report.sum_checks.append(
            SumCheck("products", "gst_rate", source_rate_sum, target_rate_sum)
        )
        self._fail_if_new_mismatch()

    def _hsn_id(self, code: str | None, cache: dict[str, int]) -> int | None:
        if code is None:
            return None
        if len(code) > 10:
            raise LegacyMigrationError(
                f"Legacy HSN code {code!r} exceeds the target's 10-character limit."
            )
        if code in cache:
            return cache[code]
        existing = self.session.scalar(
            select(HsnCode).where(HsnCode.code == code, HsnCode.deleted_at.is_(None))
        )
        if existing is None:
            existing = HsnCode(
                code=code,
                description=f"Imported legacy HSN code {code}",
                default_tax_rate_id=None,
                created_by=self.user_id,
            )
            self.session.add(existing)
            self.session.flush()
            self.report.defaults_used.append(
                f"hsn_codes[{code}].description documents the absent legacy description."
            )
        cache[code] = existing.id
        return existing.id

    def _migrate_customers(self) -> None:
        rows = _rows(self.source, "customers")
        used_phones: set[str] = set()
        for row in rows:
            legacy_id = int(row["id"])
            phone = self._normalized_optional(row["phone"])
            if phone is None or phone in used_phones:
                phone = f"LEGACY-{legacy_id}"
                self.report.defaults_used.append(
                    f"customers[{legacy_id}].phone = {phone}; legacy phone was "
                    "missing or duplicate."
                )
            used_phones.add(phone)
            raw_gstin = self._normalized_optional(row["gstin"])
            gstin = raw_gstin.upper() if raw_gstin and validate_gstin(raw_gstin) else None
            if raw_gstin and gstin is None:
                self.report.skipped.append(
                    f"customers[{legacy_id}].gstin {raw_gstin!r} was invalid and was not imported."
                )
            state_code = state_code_from_gstin(gstin) if gstin else self.config.company.state_code
            customer = Customer(
                company_id=self.company_id,
                phone=phone,
                name=str(row["name"]),
                email=self._normalized_optional(row["email"]),
                gstin=gstin,
                state_code=state_code,
                loyalty_points=_legacy_qty(row["points"]),
                total_spent=ZERO,
                total_orders=0,
                created_at=_utc_datetime(row["created_at"]),
                created_by=self.user_id,
            )
            self.session.add(customer)
            self.session.flush()
            self.customer_ids[legacy_id] = customer.id
            self._map(
                "customers",
                legacy_id,
                "customers",
                customer.id,
                at=_utc_datetime(row["created_at"]),
            )
        self._count_check("customers", Customer)
        self._sum_check(
            "customers",
            "points",
            _source_sum(self.source, "customers", "points"),
            Customer.loyalty_points,
        )
        self._fail_if_new_mismatch()

    def _prepare_sales(self) -> None:
        item_rows = _rows(self.source, "sale_items")
        by_sale: dict[int, list[sqlite3.Row]] = {}
        for item in item_rows:
            by_sale.setdefault(int(item["sale_id"]), []).append(item)
        sale_rows = sorted(
            _rows(self.source, "sales"),
            key=lambda row: (_utc_datetime(row["created_at"]), int(row["id"])),
        )
        for sequence, row in enumerate(sale_rows, start=1):
            legacy_id = int(row["id"])
            timestamp = _utc_datetime(row["created_at"])
            business_day = _business_date(timestamp, self.config.day_close_hour)
            if business_day != timestamp.date():
                self.report.business_day_shifts += 1
            invoice_number = f"LEGACY/{financial_year_code(business_day)}/{sequence:06d}"
            lines = tuple(sorted(by_sale.get(legacy_id, []), key=lambda item: int(item["id"])))
            if not lines:
                raise LegacyMigrationError(f"sales[{legacy_id}] has no sale_items.")
            tax_inputs = [
                TaxLineInput(
                    quantity=_legacy_qty(item["quantity"]),
                    unit_price=_legacy_money(item["price"]),
                    tax_rate=_legacy_money(item["gst_rate"]),
                    tax_inclusive=True,
                )
                for item in lines
            ]
            customer_id = row["customer_id"]
            place_of_supply = self.config.branch.state_code
            if customer_id is not None:
                target_customer_id = self._required_mapping(
                    self.customer_ids, customer_id, "customer", legacy_id
                )
                customer = self.session.get(Customer, target_customer_id)
                if customer is None:
                    raise LegacyMigrationError(
                        f"sales[{legacy_id}] references an unavailable customer."
                    )
                place_of_supply = customer.state_code
            result = TaxEngine.compute(
                tax_inputs,
                supplier_state=self.config.branch.state_code,
                place_of_supply=place_of_supply,
                order_discount=_legacy_money(row["discount"]),
                apply_round_off=False,
            )
            legacy_gross = money(sum((_legacy_money(item["subtotal"]) for item in lines), ZERO))
            if legacy_gross != result.gross_amount:
                raise LegacyMigrationError(
                    f"sales[{legacy_id}] item subtotals {legacy_gross} do not match "
                    f"quantity x price {result.gross_amount}."
                )
            self._record_tax_correction(row, invoice_number, result)
            self.prepared_sales.append(
                _PreparedSale(
                    row=row,
                    item_rows=lines,
                    timestamp=timestamp,
                    business_date=business_day,
                    invoice_number=invoice_number,
                    calculation=result,
                )
            )

    def _record_tax_correction(
        self, row: sqlite3.Row, invoice_number: str, result: TaxResult
    ) -> None:
        original = (
            _legacy_money(row["subtotal"]),
            _legacy_money(row["total_cgst"]),
            _legacy_money(row["total_sgst"]),
            ZERO,
            ZERO,
            ZERO,
            _legacy_money(row["total"]),
        )
        corrected = (
            result.taxable_amount,
            result.cgst_amount,
            result.sgst_amount,
            result.igst_amount,
            result.cess_amount,
            result.round_off,
            result.net_amount,
        )
        if original == corrected:
            return
        self.report.tax_corrections.append(
            TaxCorrection(
                legacy_sale_id=int(row["id"]),
                invoice_number=invoice_number,
                original_taxable=original[0],
                original_cgst=original[1],
                original_sgst=original[2],
                original_igst=original[3],
                original_cess=original[4],
                original_round_off=original[5],
                original_net=original[6],
                corrected_taxable=corrected[0],
                corrected_cgst=corrected[1],
                corrected_sgst=corrected[2],
                corrected_igst=corrected[3],
                corrected_cess=corrected[4],
                corrected_round_off=corrected[5],
                corrected_net=corrected[6],
            )
        )

    def _migrate_sales(self) -> None:
        valid_methods = {method.value for method in PaymentMethod}
        customer_totals: dict[int, Decimal] = {}
        customer_orders: dict[int, int] = {}
        for prepared in self.prepared_sales:
            row = prepared.row
            legacy_id = int(row["id"])
            result = prepared.calculation
            raw_customer_id = row["customer_id"]
            customer_id = (
                None
                if raw_customer_id is None
                else self._required_mapping(
                    self.customer_ids, raw_customer_id, "customer", legacy_id
                )
            )
            cancelled_raw = dict(row).get("cancelled_at")
            cancelled_at = _utc_datetime(cancelled_raw) if cancelled_raw else None
            if cancelled_at:
                self.report.skipped.append(
                    f"sales[{legacy_id}].cancellation_reason was unavailable in the legacy schema."
                )
            raw_method = str(row["payment_method"] or "").strip().upper()
            method = raw_method if raw_method in valid_methods else PaymentMethod.OTHER.value
            if method == PaymentMethod.OTHER.value and raw_method != PaymentMethod.OTHER.value:
                self.report.defaults_used.append(
                    f"sales[{legacy_id}].payment_method = OTHER; legacy value was {raw_method!r}."
                )
            amount_paid = _legacy_money(row["amount_paid"])
            sale = Sale(
                company_id=self.company_id,
                branch_id=self.branch_id,
                terminal_id=self.terminal_id,
                customer_id=customer_id,
                cashier_id=self.user_id,
                shift_id=None,
                invoice_number=prepared.invoice_number,
                business_date=prepared.business_date,
                sale_status=(
                    SaleStatus.CANCELLED.value if cancelled_at else SaleStatus.COMPLETED.value
                ),
                supply_type=(
                    SupplyType.INTERSTATE.value
                    if result.is_interstate
                    else SupplyType.INTRASTATE.value
                ),
                gross_amount=result.gross_amount,
                discount_amount=result.discount_amount,
                taxable_amount=result.taxable_amount,
                cgst_amount=result.cgst_amount,
                sgst_amount=result.sgst_amount,
                igst_amount=result.igst_amount,
                cess_amount=result.cess_amount,
                round_off=result.round_off,
                net_amount=result.net_amount,
                amount_paid=amount_paid,
                balance_due=money(max(result.net_amount - amount_paid, ZERO)),
                payment_method=method,
                cancelled_at=cancelled_at,
                notes=self._normalized_optional(row["notes"]),
                created_at=prepared.timestamp,
                created_by=self.user_id,
            )
            self.session.add(sale)
            self.session.flush()
            self.sale_ids[legacy_id] = sale.id
            self._map("sales", legacy_id, "sales", sale.id, at=prepared.timestamp)

            self.session.add(
                SalePayment(
                    company_id=self.company_id,
                    sale_id=sale.id,
                    payment_method=method,
                    amount=amount_paid,
                    processed_at=prepared.timestamp,
                    created_at=prepared.timestamp,
                    created_by=self.user_id,
                )
            )
            for line_number, (item_row, line) in enumerate(
                zip(prepared.item_rows, result.lines, strict=True), start=1
            ):
                half_rate = money(line.tax_rate / Decimal("2"))
                item = SaleItem(
                    company_id=self.company_id,
                    sale_id=sale.id,
                    product_id=self._required_mapping(
                        self.product_ids, item_row["product_id"], "product", int(item_row["id"])
                    ),
                    line_number=line_number,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    gross_amount=line.gross_amount,
                    discount_amount=line.discount_amount,
                    taxable_amount=line.taxable_amount,
                    tax_rate=line.tax_rate,
                    cgst_rate=ZERO if result.is_interstate else half_rate,
                    sgst_rate=ZERO if result.is_interstate else half_rate,
                    igst_rate=line.tax_rate if result.is_interstate else ZERO,
                    cess_rate=line.cess_rate,
                    cgst_amount=line.cgst_amount,
                    sgst_amount=line.sgst_amount,
                    igst_amount=line.igst_amount,
                    cess_amount=line.cess_amount,
                    total_amount=line.line_total,
                    created_at=prepared.timestamp,
                    created_by=self.user_id,
                )
                self.session.add(item)
                self.session.flush()
                legacy_item_id = int(item_row["id"])
                self.sale_item_ids[legacy_item_id] = item.id
                self._map(
                    "sale_items", legacy_item_id, "sale_items", item.id, at=prepared.timestamp
                )

            if customer_id is not None:
                customer_totals[customer_id] = money(
                    customer_totals.get(customer_id, ZERO) + result.net_amount
                )
                customer_orders[customer_id] = customer_orders.get(customer_id, 0) + 1

        for customer_id, total in customer_totals.items():
            customer = self.session.get(Customer, customer_id)
            if customer is None:
                raise LegacyMigrationError(f"Imported customer {customer_id} disappeared.")
            customer.total_spent = total
            customer.total_orders = customer_orders[customer_id]
        self.session.flush()
        self._verify_sales()
        self._fail_if_new_mismatch()

    def _verify_sales(self) -> None:
        self._count_check("sales", Sale)
        self._count_check("sale_items", SaleItem)
        self.report.row_counts["sale_payments"] = (
            _source_count(self.source, "sales"),
            self._target_count(SalePayment),
        )
        expected = {
            "subtotal": money(
                sum((sale.calculation.taxable_amount for sale in self.prepared_sales), ZERO)
            ),
            "total_cgst": money(
                sum((sale.calculation.cgst_amount for sale in self.prepared_sales), ZERO)
            ),
            "total_sgst": money(
                sum((sale.calculation.sgst_amount for sale in self.prepared_sales), ZERO)
            ),
            "total": _source_sum(self.source, "sales", "total"),
            "discount": _source_sum(self.source, "sales", "discount"),
            "amount_paid": _source_sum(self.source, "sales", "amount_paid"),
        }
        target_fields = {
            "subtotal": Sale.taxable_amount,
            "total_cgst": Sale.cgst_amount,
            "total_sgst": Sale.sgst_amount,
            "total": Sale.net_amount,
            "discount": Sale.discount_amount,
            "amount_paid": Sale.amount_paid,
        }
        for field_name, expected_sum in expected.items():
            self._sum_check("sales", field_name, expected_sum, target_fields[field_name])
        self.report.sum_checks.extend(
            [
                SumCheck(
                    "sales",
                    "change_given (derived)",
                    _source_sum(self.source, "sales", "change_given"),
                    money(
                        sum(
                            (
                                _legacy_money(sale.row["amount_paid"]) - sale.calculation.net_amount
                                for sale in self.prepared_sales
                            ),
                            ZERO,
                        )
                    ),
                ),
                SumCheck(
                    "sale_items",
                    "price",
                    _source_sum(self.source, "sale_items", "price"),
                    self._target_sum(SaleItem.unit_price),
                ),
                SumCheck(
                    "sale_items",
                    "gst_rate",
                    _source_sum(self.source, "sale_items", "gst_rate"),
                    self._target_sum(SaleItem.tax_rate),
                ),
                SumCheck(
                    "sale_items",
                    "quantity",
                    _source_sum(self.source, "sale_items", "quantity"),
                    self._target_sum(SaleItem.quantity),
                ),
                SumCheck(
                    "sale_items",
                    "subtotal/gross_amount",
                    _source_sum(self.source, "sale_items", "subtotal"),
                    self._target_sum(SaleItem.gross_amount),
                ),
            ]
        )

    def _migrate_returns(self) -> None:
        return_rows = sorted(
            _rows(self.source, "sale_returns"),
            key=lambda row: (_utc_datetime(row["created_at"]), int(row["id"])),
        )
        return_item_rows = _rows(self.source, "sale_return_items")
        by_return: dict[int, list[sqlite3.Row]] = {}
        for item in return_item_rows:
            by_return.setdefault(int(item["sale_return_id"]), []).append(item)
        source_sale_items = _rows(self.source, "sale_items")
        original_by_sale_product: dict[tuple[int, int], list[int]] = {}
        sold_qty_by_sale: dict[int, Decimal] = {}
        for item in source_sale_items:
            key = (int(item["sale_id"]), int(item["product_id"]))
            original_by_sale_product.setdefault(key, []).append(int(item["id"]))
            sale_id = int(item["sale_id"])
            sold_qty_by_sale[sale_id] = qty(
                sold_qty_by_sale.get(sale_id, qty(ZERO)) + _legacy_qty(item["quantity"])
            )
        returned_qty_by_sale: dict[int, Decimal] = {}
        reasons = {reason.value for reason in ReturnReason}
        for sequence, row in enumerate(return_rows, start=1):
            legacy_id = int(row["id"])
            legacy_sale_id = int(row["sale_id"])
            timestamp = _utc_datetime(row["created_at"])
            business_day = _business_date(timestamp, self.config.day_close_hour)
            reason_text = str(row["reason"] or "").strip()
            normalized_reason = reason_text.upper().replace("-", "_").replace(" ", "_")
            reason = normalized_reason if normalized_reason in reasons else ReturnReason.OTHER.value
            if reason == ReturnReason.OTHER.value and normalized_reason != ReturnReason.OTHER.value:
                self.report.skipped.append(
                    f"sale_returns[{legacy_id}].reason {reason_text!r} had no target enum; "
                    "stored as OTHER."
                )
            payment_method = str(row["payment_method"] or "").strip()
            if payment_method:
                self.report.skipped.append(
                    f"sale_returns[{legacy_id}].payment_method {payment_method!r} has no "
                    "credit-note field."
                )
            credit_note = CreditNote(
                company_id=self.company_id,
                branch_id=self.branch_id,
                original_sale_id=self._required_mapping(
                    self.sale_ids, legacy_sale_id, "sale", legacy_id
                ),
                credit_note_number=(
                    f"LEGACY-CN/{financial_year_code(business_day)}/{sequence:06d}"
                ),
                note_date=business_day,
                reason=reason,
                net_amount=_legacy_money(row["refund_amount"]),
                created_at=timestamp,
                created_by=self.user_id,
            )
            self.session.add(credit_note)
            self.session.flush()
            self.credit_note_ids[legacy_id] = credit_note.id
            self._map("sale_returns", legacy_id, "credit_notes", credit_note.id, at=timestamp)

            for item_row in sorted(by_return.get(legacy_id, []), key=lambda item: int(item["id"])):
                product_id = int(item_row["product_id"])
                candidates = original_by_sale_product.get((legacy_sale_id, product_id), [])
                if len(candidates) != 1:
                    raise LegacyMigrationError(
                        f"sale_return_items[{int(item_row['id'])}] cannot be mapped "
                        "unambiguously to one original sale item."
                    )
                original_item_id = self._required_mapping(
                    self.sale_item_ids, candidates[0], "sale_item", int(item_row["id"])
                )
                credit_item = CreditNoteItem(
                    company_id=self.company_id,
                    credit_note_id=credit_note.id,
                    original_sale_item_id=original_item_id,
                    quantity=_legacy_qty(item_row["quantity"]),
                    amount=_legacy_money(item_row["subtotal"]),
                    created_at=timestamp,
                    created_by=self.user_id,
                )
                self.session.add(credit_item)
                self.session.flush()
                self._map(
                    "sale_return_items",
                    int(item_row["id"]),
                    "credit_note_items",
                    credit_item.id,
                    at=timestamp,
                )
                returned_qty_by_sale[legacy_sale_id] = qty(
                    returned_qty_by_sale.get(legacy_sale_id, qty(ZERO))
                    + _legacy_qty(item_row["quantity"])
                )

        for legacy_sale_id, returned in returned_qty_by_sale.items():
            sale = self.session.get(Sale, self.sale_ids[legacy_sale_id])
            if sale is None or sale.sale_status == SaleStatus.CANCELLED.value:
                continue
            sale.sale_status = (
                SaleStatus.RETURNED.value
                if returned >= sold_qty_by_sale[legacy_sale_id]
                else SaleStatus.PARTIALLY_RETURNED.value
            )
        self.session.flush()
        self._verify_returns(return_item_rows)
        self._fail_if_new_mismatch()

    def _verify_returns(self, return_item_rows: list[sqlite3.Row]) -> None:
        self.report.row_counts["sale_returns/credit_notes"] = (
            _source_count(self.source, "sale_returns"),
            self._target_count(CreditNote),
        )
        self.report.row_counts["sale_return_items/credit_note_items"] = (
            _source_count(self.source, "sale_return_items"),
            self._target_count(CreditNoteItem),
        )
        self._sum_check(
            "sale_returns",
            "refund_amount",
            _source_sum(self.source, "sale_returns", "refund_amount"),
            CreditNote.net_amount,
        )
        self._sum_check(
            "sale_return_items",
            "quantity",
            _source_sum(self.source, "sale_return_items", "quantity"),
            CreditNoteItem.quantity,
        )
        self._sum_check(
            "sale_return_items",
            "subtotal/amount",
            _source_sum(self.source, "sale_return_items", "subtotal"),
            CreditNoteItem.amount,
        )
        derived_prices = money(
            sum(
                (
                    _legacy_money(row["subtotal"]) / _legacy_qty(row["quantity"])
                    for row in return_item_rows
                ),
                ZERO,
            )
        )
        self.report.sum_checks.append(
            SumCheck(
                "sale_return_items",
                "price (derived)",
                _source_sum(self.source, "sale_return_items", "price"),
                derived_prices,
            )
        )

    def _map(
        self,
        legacy_table: str,
        legacy_id: int,
        target_table: str,
        target_id: int,
        *,
        at: datetime | None = None,
    ) -> None:
        self.session.add(
            LegacyIdMap(
                company_id=self.company_id,
                legacy_table=legacy_table,
                legacy_id=str(legacy_id),
                target_table=target_table,
                target_id=target_id,
                created_at=at or datetime.now(UTC),
                created_by=self.user_id,
            )
        )

    def _count_check(self, source_table: str, target_model: type[TenantEntity]) -> None:
        self.report.row_counts[source_table] = (
            _source_count(self.source, source_table),
            self._target_count(target_model),
        )

    def _target_count(self, target_model: type[TenantEntity]) -> int:
        company_column = target_model.company_id
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(target_model)
                .where(company_column == self.company_id)
            )
            or 0
        )

    def _sum_check(
        self,
        table: str,
        field_name: str,
        source: Decimal,
        target_column: InstrumentedAttribute[Decimal],
    ) -> None:
        self.report.sum_checks.append(
            SumCheck(table, field_name, source, self._target_sum(target_column))
        )

    def _target_sum(self, target_column: InstrumentedAttribute[Decimal]) -> Decimal:
        model = target_column.class_
        value = self.session.scalar(
            select(func.coalesce(func.sum(target_column), 0)).where(
                model.company_id == self.company_id
            )
        )
        return _legacy_money(value)

    def _fail_if_new_mismatch(self) -> None:
        bad_counts = [
            table for table, (source, target) in self.report.row_counts.items() if source != target
        ]
        bad_sums = [
            f"{check.table}.{check.field}" for check in self.report.sum_checks if not check.matches
        ]
        if bad_counts or bad_sums:
            details = ", ".join(bad_counts + bad_sums)
            raise LegacyMigrationError(f"Migration verification failed: {details}")

    def _verify_all_checks(self) -> None:
        expected_maps = sum(target for _, target in self.report.row_counts.values())
        actual_maps = self._target_count(LegacyIdMap)
        # Sale payments and stock rows have no legacy IDs of their own.
        expected_maps -= self.report.row_counts.get("sale_payments", (0, 0))[1]
        expected_maps -= self.report.row_counts.get("stock_ledger (OPENING)", (0, 0))[1]
        self.report.row_counts["legacy_id_map"] = (expected_maps, actual_maps)
        self._fail_if_new_mismatch()

    @staticmethod
    def _normalized_optional(value: object | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _mapped_optional(
        mapping: dict[int, int], value: object | None, label: str, owner_id: int
    ) -> int | None:
        if value is None:
            return None
        return LegacyMigrator._required_mapping(mapping, value, label, owner_id)

    @staticmethod
    def _required_mapping(mapping: dict[int, int], value: object, label: str, owner_id: int) -> int:
        try:
            return mapping[int(str(value))]
        except (KeyError, TypeError, ValueError) as exc:
            raise LegacyMigrationError(
                f"Legacy row {owner_id} references missing {label} ID {value!r}."
            ) from exc


def migrate_legacy_database(
    session: Session,
    *,
    legacy_database: Path,
    config_file: Path,
    output_dir: Path,
    dry_run: bool,
    apply_tax_corrections: bool,
) -> MigrationReport:
    """Run a snapshot-based migration and always emit its review artifacts."""
    backup_file = backup_legacy_database(legacy_database)
    report = MigrationReport(
        legacy_database=legacy_database,
        backup_file=backup_file,
        config_file=config_file,
        dry_run=dry_run,
        apply_tax_corrections=apply_tax_corrections,
    )
    try:
        config = _load_config(config_file)
        with closing(sqlite3.connect(f"file:{backup_file.as_posix()}?mode=ro", uri=True)) as source:
            source.row_factory = sqlite3.Row
            LegacyMigrator(
                session,
                source,
                config,
                report,
                apply_tax_corrections=apply_tax_corrections,
            ).run()
        if dry_run:
            session.rollback()
            report.status = "DRY-RUN PASSED"
        else:
            session.commit()
            report.status = "COMPLETED"
    except (LegacyMigrationError, SQLAlchemyError, sqlite3.Error, ValueError) as exc:
        session.rollback()
        report.status = "FAILED"
        report.skipped.append(f"Migration aborted: {exc}")
        report.write(output_dir)
        if isinstance(exc, LegacyMigrationError):
            raise
        raise LegacyMigrationError(str(exc)) from exc
    report.write(output_dir)
    return report


@click.command("migrate-legacy")
@click.option(
    "--legacy-db",
    "legacy_database",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("legacy/instance/pos.db"),
    show_default=True,
)
@click.option(
    "--config",
    "config_file",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("legacy_migration.json"),
    show_default=True,
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("."),
    show_default=True,
)
@click.option("--dry-run", is_flag=True, help="Validate and report, then roll back all rows.")
@click.option(
    "--apply-tax-corrections",
    is_flag=True,
    help="Apply TaxEngine values recorded in the accountant correction CSV.",
)
@with_appcontext
def migrate_legacy(
    legacy_database: Path,
    config_file: Path,
    output_dir: Path,
    dry_run: bool,
    apply_tax_corrections: bool,
) -> None:
    """Import the prototype database only after a complete reconciliation pass."""
    try:
        with Session(db.engine, expire_on_commit=False) as session:
            report = migrate_legacy_database(
                session,
                legacy_database=legacy_database,
                config_file=config_file,
                output_dir=output_dir,
                dry_run=dry_run,
                apply_tax_corrections=apply_tax_corrections,
            )
    except LegacyMigrationError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"Legacy migration {report.status.lower()}; backup: {report.backup_file}; "
        f"report: {output_dir / 'MIGRATION_REPORT.md'}"
    )
