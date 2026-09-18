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
    assert len(inspect(engine).get_table_names()) == 31  # 30 domain tables + alembic_version
    assert "mv_daily_sales_summary" in inspect(engine).get_view_names()
    engine.dispose()
    command.check(config)

    command.downgrade(config, "base")
    engine = create_engine(database_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    assert len(inspect(engine).get_table_names()) == 31
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
    }
    for index_name in concurrent_indexes:
        assert f"INDEX CONCURRENTLY {index_name}" in sql

    assert "CREATE MATERIALIZED VIEW mv_daily_sales_summary" in sql
    assert "old_values JSONB" in sql
    assert "new_values JSONB" in sql
    assert "CREATE TABLE audit_log_y2026m07 PARTITION OF audit_log" in sql
    assert "CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT" in sql
