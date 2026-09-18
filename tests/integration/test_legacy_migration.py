"""Phase 1E integration coverage for the all-or-nothing legacy importer."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.app import create_app
from vglpos.cli.legacy_migration import (
    LegacyMigrationError,
    backup_legacy_database,
    migrate_legacy_database,
)
from vglpos.config import TestingConfig
from vglpos.domain.models import (
    Company,
    CreditNote,
    Customer,
    LegacyIdMap,
    Product,
    Sale,
    SaleItem,
    StockLedger,
)
from vglpos.extensions import db


def _create_legacy_database(
    path: Path, *, broken_tax: bool = False, include_return: bool = True
) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, icon TEXT
        );
        CREATE TABLE products (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL,
            barcode TEXT, price REAL NOT NULL, cost REAL, stock INTEGER,
            low_stock_threshold INTEGER, category_id INTEGER, gst_rate REAL,
            hsn_code TEXT, active INTEGER, created_at TEXT
        );
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT, phone TEXT,
            gstin TEXT, points INTEGER, created_at TEXT
        );
        CREATE TABLE sales (
            id INTEGER PRIMARY KEY, customer_id INTEGER, subtotal REAL,
            total_cgst REAL, total_sgst REAL, total REAL, discount REAL,
            amount_paid REAL, change_given REAL, payment_method TEXT, notes TEXT,
            created_at TEXT, cancelled_at TEXT
        );
        CREATE TABLE sale_items (
            id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL, price REAL NOT NULL, gst_rate REAL,
            subtotal REAL NOT NULL
        );
        CREATE TABLE sale_returns (
            id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL, refund_amount REAL,
            payment_method TEXT, reason TEXT, created_at TEXT
        );
        CREATE TABLE sale_return_items (
            id INTEGER PRIMARY KEY, sale_return_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL, quantity INTEGER NOT NULL,
            price REAL NOT NULL, subtotal REAL NOT NULL
        );
        """
    )
    price = 299.0 if broken_tax else 118.0
    quantity = 1 if broken_tax else 2
    gross = 299.0 if broken_tax else 236.0
    taxable = 253.39 if broken_tax else 200.0
    component_tax = 22.81 if broken_tax else 18.0
    discount = 50.0 if broken_tax else 0.0
    net = 249.0 if broken_tax else 236.0
    tendered = 300.0 if broken_tax else 250.004
    change_given = 51.0 if broken_tax else 14.0
    connection.execute("INSERT INTO categories VALUES (1, 'General', 'box')")
    connection.execute(
        "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "Legacy Product",
            "LEG-001",
            "890000000001",
            price,
            75.0,
            7,
            2,
            1,
            18.0,
            "1001",
            1,
            "2026-04-01 10:00:00",
        ),
    )
    connection.execute(
        "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "Legacy Customer",
            "legacy@example.invalid",
            "9000000001",
            None,
            5,
            "2026-04-01 11:00:00",
        ),
    )
    connection.execute(
        "INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            1,
            taxable,
            component_tax,
            component_tax,
            net,
            discount,
            tendered,
            change_given,
            "cash",
            "Imported sale",
            "2026-04-01 20:00:00",
            None,
        ),
    )
    connection.execute(
        "INSERT INTO sale_items VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, 1, 1, quantity, price, 18.0, gross),
    )
    if include_return:
        connection.execute(
            "INSERT INTO sale_returns VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, 118.0, "cash", "customer request", "2026-04-02 08:00:00"),
        )
        connection.execute(
            "INSERT INTO sale_return_items VALUES (?, ?, ?, ?, ?, ?)",
            (1, 1, 1, 1, 118.0, 118.0),
        )
    connection.commit()
    connection.close()


def _write_config(path: Path) -> None:
    config = {
        "company": {
            "name": "Migration Test Company",
            "legal_name": "Migration Test Company Private Limited",
            "login_code": "MIGRATION-TEST",
            "state_code": "33",
            "address_line1": "1 Test Street",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "postal_code": "600001",
            "contact_email": "company@example.invalid",
            "contact_phone": "9000000000",
        },
        "branch": {
            "code": "MAIN",
            "name": "Main Branch",
            "state_code": "33",
            "address_line1": "1 Test Street",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "postal_code": "600001",
            "phone": "9000000000",
        },
        "terminal": {"code": "T01", "name": "Counter 1"},
        "system_user": {
            "email": "legacy-import@example.invalid",
            "password_hash": "not-a-real-password-hash",
        },
        "day_close_hour": 0,
    }
    path.write_text(json.dumps(config), encoding="utf-8")


def _paths(tmp_path: Path, *, broken_tax: bool = False) -> tuple[Path, Path, Path]:
    legacy = tmp_path / "legacy.db"
    config = tmp_path / "legacy_migration.json"
    output = tmp_path / "reports"
    _create_legacy_database(legacy, broken_tax=broken_tax, include_return=not broken_tax)
    _write_config(config)
    return legacy, config, output


def test_backup_consolidates_uncheckpointed_wal_pages(tmp_path: Path) -> None:
    source = tmp_path / "wal-source.db"
    connection = sqlite3.connect(source)
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)")
    connection.execute("INSERT INTO evidence (value) VALUES ('from-wal')")
    connection.commit()

    backup = backup_legacy_database(source)

    with closing(sqlite3.connect(backup)) as snapshot:
        assert snapshot.execute("SELECT value FROM evidence").fetchone()[0] == "from-wal"
    connection.close()


def test_dry_run_emits_reports_and_rolls_back_all_target_rows(
    service_session: Session, tmp_path: Path
) -> None:
    legacy, config, output = _paths(tmp_path)

    report = migrate_legacy_database(
        service_session,
        legacy_database=legacy,
        config_file=config,
        output_dir=output,
        dry_run=True,
        apply_tax_corrections=False,
    )

    assert report.status == "DRY-RUN PASSED"
    assert report.backup_file.exists()
    assert (output / "MIGRATION_REPORT.md").exists()
    assert (output / "MIGRATION_TAX_CORRECTIONS.csv").exists()
    assert service_session.scalar(select(func.count()).select_from(Company)) == 0
    assert service_session.scalar(select(func.count()).select_from(Sale)) == 0


def test_applied_import_reconciles_money_stock_returns_and_provenance(
    service_session: Session, tmp_path: Path
) -> None:
    legacy, config, output = _paths(tmp_path)

    report = migrate_legacy_database(
        service_session,
        legacy_database=legacy,
        config_file=config,
        output_dir=output,
        dry_run=False,
        apply_tax_corrections=False,
    )

    sale = service_session.scalar(select(Sale))
    product = service_session.scalar(select(Product))
    customer = service_session.scalar(select(Customer))
    assert report.status == "COMPLETED"
    assert report.business_day_shifts == 1
    assert report.tax_corrections == []
    assert sale is not None
    assert sale.invoice_number == "LEGACY/26-27/000001"
    assert sale.business_date == date(2026, 4, 2)
    assert sale.taxable_amount == Decimal("200.00")
    assert sale.cgst_amount == Decimal("18.00")
    assert sale.sgst_amount == Decimal("18.00")
    assert sale.net_amount == Decimal("236.00")
    assert sale.amount_paid == Decimal("250.00")
    assert sale.sale_status == "PARTIALLY_RETURNED"
    assert product is not None
    assert product.on_hand == Decimal("7.000")
    assert customer is not None
    assert customer.total_spent == Decimal("236.00")
    assert customer.total_orders == 1
    assert service_session.scalar(select(func.count()).select_from(SaleItem)) == 1
    assert service_session.scalar(select(func.count()).select_from(CreditNote)) == 1
    assert service_session.scalar(select(func.count()).select_from(StockLedger)) == 1
    assert service_session.scalar(select(func.count()).select_from(LegacyIdMap)) == 8
    assert all(check.matches for check in report.sum_checks)

    with pytest.raises(LegacyMigrationError, match="already contains 1 sale"):
        migrate_legacy_database(
            service_session,
            legacy_database=legacy,
            config_file=config,
            output_dir=output,
            dry_run=False,
            apply_tax_corrections=False,
        )
    assert service_session.scalar(select(func.count()).select_from(Company)) == 1


def test_tax_correction_requires_flag_and_imports_reviewed_values(
    service_session: Session, tmp_path: Path
) -> None:
    legacy, config, output = _paths(tmp_path, broken_tax=True)

    dry_report = migrate_legacy_database(
        service_session,
        legacy_database=legacy,
        config_file=config,
        output_dir=output,
        dry_run=True,
        apply_tax_corrections=False,
    )
    assert len(dry_report.tax_corrections) == 1
    correction = dry_report.tax_corrections[0]
    assert correction.original_taxable == Decimal("253.39")
    assert correction.corrected_taxable == Decimal("211.02")
    assert correction.corrected_cgst == Decimal("18.99")
    assert correction.corrected_sgst == Decimal("18.99")
    assert correction.corrected_net == Decimal("249.00")

    with pytest.raises(LegacyMigrationError, match="accountant approval"):
        migrate_legacy_database(
            service_session,
            legacy_database=legacy,
            config_file=config,
            output_dir=output,
            dry_run=False,
            apply_tax_corrections=False,
        )
    assert service_session.scalar(select(func.count()).select_from(Company)) == 0

    report = migrate_legacy_database(
        service_session,
        legacy_database=legacy,
        config_file=config,
        output_dir=output,
        dry_run=False,
        apply_tax_corrections=True,
    )
    sale = service_session.scalar(select(Sale))
    assert report.status == "COMPLETED"
    assert sale is not None
    assert sale.taxable_amount == Decimal("211.02")
    assert sale.cgst_amount == Decimal("18.99")
    assert sale.sgst_amount == Decimal("18.99")
    assert sale.net_amount == Decimal("249.00")
    assert "253.39" in (output / "MIGRATION_TAX_CORRECTIONS.csv").read_text(encoding="utf-8")


def test_p0_4_sqlite_constraint_accepts_exact_299_discount_regression(
    service_session: Session, tmp_path: Path
) -> None:
    legacy, config, output = _paths(tmp_path, broken_tax=True)

    migrate_legacy_database(
        service_session,
        legacy_database=legacy,
        config_file=config,
        output_dir=output,
        dry_run=False,
        apply_tax_corrections=True,
    )

    sale = service_session.scalar(select(Sale))
    assert sale is not None
    money_sum = (
        sale.taxable_amount
        + sale.cgst_amount
        + sale.sgst_amount
        + sale.igst_amount
        + sale.cess_amount
        + sale.round_off
    )
    assert money_sum == sale.net_amount == Decimal("249.00")


def test_flask_app_registers_migrate_legacy_command(app: Flask) -> None:
    assert "migrate-legacy" in app.cli.commands


def test_flask_migrate_legacy_dry_run_gate(tmp_path: Path) -> None:
    legacy, config, output = _paths(tmp_path)
    target = tmp_path / "phase1e_cli_test"

    class CliTestingConfig(TestingConfig):
        DATABASE_URL: str = f"sqlite+pysqlite:///{target.as_posix()}"

    application = create_app(CliTestingConfig)
    with application.app_context():
        db.create_all()
        result = application.test_cli_runner().invoke(
            args=[
                "migrate-legacy",
                "--legacy-db",
                str(legacy),
                "--config",
                str(config),
                "--output-dir",
                str(output),
                "--dry-run",
            ]
        )
        assert result.exit_code == 0, result.output
        assert "dry-run passed" in result.output
        assert db.session.scalar(select(func.count()).select_from(Sale)) == 0
        db.session.remove()
        db.drop_all()
