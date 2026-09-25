"""Exercise the complete Alembic upgrade/downgrade chain against scratch SQLite."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.mark.usefixtures("_assert_test_database")
def test_all_migrations_upgrade_downgrade_and_reupgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "migration_test.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    assert len(inspect(engine).get_table_names()) == 48  # 47 domain tables + alembic_version
    assert "mv_daily_sales_summary" in inspect(engine).get_view_names()
    assert "total_cess" in (inspect(engine).get_view_definition("mv_daily_sales_summary") or "")
    assert {
        "idx_sales_company_branch_created",
        "idx_sales_company_branch_status_date",
    }.issubset({index["name"] for index in inspect(engine).get_indexes("sales")})
    assert {"name_en", "name_ta", "is_weighed"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("products")}
    )
    assert {"name_en", "name_ta"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("categories")}
    )
    assert {"held_bills", "loyalty_ledger", "terminal_quick_keys"}.issubset(
        inspect(engine).get_table_names()
    )
    assert {
        "opening_denominations",
        "closing_denominations",
        "variance_approved_by",
        "variance_reason",
    }.issubset({column["name"] for column in inspect(engine).get_columns("shifts")})
    assert {
        "goods_receipts",
        "goods_receipt_items",
        "credit_note_item_batches",
        "purchase_orders",
        "purchase_order_items",
        "purchase_returns",
        "purchase_return_items",
        "report_jobs",
        "sale_item_batches",
        "stock_audits",
        "stock_audit_items",
        "stock_transfers",
        "stock_transfer_items",
        "supplier_ledger",
    }.issubset(inspect(engine).get_table_names())
    assert {
        "batch_tracking_enabled",
        "parent_product_id",
        "preferred_supplier_id",
        "safety_stock",
    }.issubset({column["name"] for column in inspect(engine).get_columns("products")})
    assert {"cost_at_sale", "hsn_code_at_sale", "supplier_id_at_sale", "uqc_at_sale"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("sale_items")}
    )
    assert {"customer_gstin_at_sale", "customer_name_at_sale", "place_of_supply"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("sales")}
    )
    assert "note_date" in {column["name"] for column in inspect(engine).get_columns("credit_notes")}
    open_shift_index = next(
        index
        for index in inspect(engine).get_indexes("shifts")
        if index["name"] == "idx_shifts_open"
    )
    assert bool(open_shift_index["unique"])
    engine.dispose()
    command.check(config)

    command.downgrade(config, "0015")
    engine = create_engine(database_url)
    assert {
        "goods_receipts",
        "credit_note_item_batches",
        "purchase_orders",
        "purchase_returns",
        "report_jobs",
        "sale_item_batches",
        "stock_audits",
        "stock_transfers",
        "supplier_ledger",
    }.isdisjoint(inspect(engine).get_table_names())
    assert "batch_tracking_enabled" not in {
        column["name"] for column in inspect(engine).get_columns("products")
    }
    engine.dispose()
    command.upgrade(config, "head")

    command.downgrade(config, "0014")
    engine = create_engine(database_url)
    assert {"held_bills", "loyalty_ledger", "terminal_quick_keys"}.isdisjoint(
        inspect(engine).get_table_names()
    )
    assert "opening_denominations" not in {
        column["name"] for column in inspect(engine).get_columns("shifts")
    }
    engine.dispose()
    command.upgrade(config, "head")

    command.downgrade(config, "0013")
    engine = create_engine(database_url)
    assert {"name_en", "name_ta", "is_weighed"}.isdisjoint(
        {column["name"] for column in inspect(engine).get_columns("products")}
    )
    assert {"name_en", "name_ta"}.isdisjoint(
        {column["name"] for column in inspect(engine).get_columns("categories")}
    )
    engine.dispose()
    command.upgrade(config, "head")

    command.downgrade(config, "0012")
    engine = create_engine(database_url)
    assert "total_cess" not in (inspect(engine).get_view_definition("mv_daily_sales_summary") or "")
    assert "idx_sales_company_branch_status_date" not in {
        index["name"] for index in inspect(engine).get_indexes("sales")
    }
    engine.dispose()
    command.upgrade(config, "head")

    command.downgrade(config, "base")
    engine = create_engine(database_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    assert len(inspect(engine).get_table_names()) == 48
    assert "mv_daily_sales_summary" in inspect(engine).get_view_names()
    engine.dispose()


def test_postgresql_offline_sql_contains_server_only_structures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg:///vglpos_test")
    config = Config("alembic.ini")

    command.upgrade(config, "head", sql=True)
    sql = capsys.readouterr().out

    concurrent_indexes = {
        "uq_products_company_sku",
        "idx_products_company_category",
        "idx_products_barcode",
        "uq_product_barcodes_code",
        "idx_product_barcodes_product",
        "uq_customers_company_phone",
        "idx_customers_company_name",
        "uq_sales_company_invoice",
        "uq_sales_company_offline_uuid",
        "idx_sales_branch_business_date",
        "idx_sales_customer",
        "idx_sale_items_sale_id",
        "idx_sale_items_product_id",
        "uq_credit_notes_number",
        "uq_batches_product_number",
        "idx_batches_expiry",
        "idx_stock_ledger_product_lookup",
        "idx_stock_ledger_reference",
        "uq_mv_daily_sales",
        "idx_products_company_created",
        "idx_customers_company_created",
        "idx_sales_company_branch_created",
        "idx_sales_company_branch_status_date",
    }
    for index_name in concurrent_indexes:
        assert f"INDEX CONCURRENTLY {index_name}" in sql

    assert "CREATE MATERIALIZED VIEW mv_daily_sales_summary" in sql
    assert "SUM(cess_amount) AS total_cess" in sql
    assert "old_values JSONB" in sql
    assert "new_values JSONB" in sql
    assert "CREATE TABLE audit_log_y2026m07 PARTITION OF audit_log" in sql
    assert "CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT" in sql
