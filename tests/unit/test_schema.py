"""Machine-enforced Phase 1B schema invariants."""

from __future__ import annotations

from dataclasses import is_dataclass
from enum import StrEnum
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, CheckConstraint, Float, Numeric, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, scoped_session

from vglpos.domain import enums, events
from vglpos.domain.models import Product, Sale, User
from vglpos.extensions import db

EXPECTED_TABLES = {
    "audit_log",
    "branches",
    "cash_movements",
    "categories",
    "companies",
    "credit_note_items",
    "credit_notes",
    "customers",
    "document_series",
    "hsn_codes",
    "legacy_id_map",
    "permissions",
    "product_barcodes",
    "product_price_history",
    "products",
    "purchase_items",
    "purchases",
    "role_permissions",
    "roles",
    "sale_items",
    "sale_payments",
    "sales",
    "shifts",
    "stock_batches",
    "stock_ledger",
    "suppliers",
    "tax_rates",
    "terminals",
    "user_roles",
    "users",
}

GLOBAL_TABLES = {"companies", "permissions", "hsn_codes"}
AUDIT_COLUMNS = {
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "deleted_at",
    "deleted_by",
    "row_version",
}
QUANTITY_COLUMNS = {
    "balance_after",
    "loyalty_points",
    "low_stock_threshold",
    "on_hand",
    "quantity",
    "quantity_available",
    "quantity_received",
    "reserved_quantity",
}
RATE_COLUMNS = {
    "rate",
    "tax_rate",
    "cgst_rate",
    "sgst_rate",
    "igst_rate",
    "cess_rate",
    "max_discount_percent",
}


@pytest.fixture(autouse=True)
def _schema(db_session: scoped_session[Session]) -> None:
    db.metadata.create_all(bind=db_session.bind)


def test_complete_target_table_set_is_registered() -> None:
    assert set(db.metadata.tables) == EXPECTED_TABLES


def test_no_float_columns_anywhere() -> None:
    for table in db.metadata.tables.values():
        for column in table.columns:
            assert not isinstance(column.type, Float), f"{table.name}.{column.name} uses Float"


def test_every_table_has_bigint_surrogate_id() -> None:
    for table in db.metadata.tables.values():
        column = table.columns.get("id")
        assert column is not None, f"{table.name} has no surrogate id"
        assert column.primary_key, f"{table.name}.id is not part of the primary key"
        assert isinstance(column.type, BigInteger), f"{table.name}.id is not BIGINT"


def test_every_table_has_complete_audit_columns() -> None:
    for table in db.metadata.tables.values():
        missing = AUDIT_COLUMNS - set(table.columns.keys())
        assert not missing, f"{table.name} missing audit columns: {sorted(missing)}"


def test_every_unique_index_honours_soft_delete() -> None:
    for table in db.metadata.tables.values():
        for index in table.indexes:
            if not index.unique:
                continue
            predicate = index.dialect_options["postgresql"].get("where")
            assert predicate is not None, f"{table.name}.{index.name} is not a partial index"
            assert "deleted_at IS NULL" in str(predicate)


def test_every_tenant_table_has_company_boundary() -> None:
    for table in db.metadata.tables.values():
        if table.name in GLOBAL_TABLES:
            continue
        company_id = table.columns.get("company_id")
        assert company_id is not None, f"{table.name} is missing company_id"
        assert company_id.nullable is False
        assert any(fk.target_fullname == "companies.id" for fk in company_id.foreign_keys)


def test_every_foreign_key_has_explicit_ondelete() -> None:
    for table in db.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            assert foreign_key.ondelete in {"RESTRICT", "CASCADE"}, (
                f"{table.name}.{foreign_key.parent.name} lacks an explicit ON DELETE policy"
            )


def test_numeric_columns_use_statutory_precision() -> None:
    for table in db.metadata.tables.values():
        for column in table.columns:
            if not isinstance(column.type, Numeric):
                continue
            if column.name in QUANTITY_COLUMNS:
                assert (column.type.precision, column.type.scale) == (12, 3), (
                    f"{table.name}.{column.name} is not NUMERIC(12,3)"
                )
            elif column.name in RATE_COLUMNS:
                assert (column.type.precision, column.type.scale) == (5, 2), (
                    f"{table.name}.{column.name} is not NUMERIC(5,2)"
                )
            else:
                assert (column.type.precision, column.type.scale) == (14, 2), (
                    f"{table.name}.{column.name} is neither a statutory rate, quantity, "
                    "nor NUMERIC(14,2) money"
                )


def test_critical_database_checks_exist() -> None:
    checks = {
        constraint.name
        for table in db.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_roles_max_discount_percent",
        "ck_tax_rates_components",
        "ck_products_prices",
        "ck_sales_reconcile",
        "ck_sales_tax_mode",
        "ck_sale_items_qty",
    } <= checks


def test_p0_4_database_rejects_unreconciled_invoice(
    db_session: scoped_session[Session],
) -> None:
    with pytest.raises(IntegrityError, match="ck_sales_reconcile"):
        db_session.execute(
            text(
                """
                INSERT INTO sales (
                    company_id, branch_id, terminal_id, cashier_id,
                    invoice_number, business_date, sale_status, supply_type,
                    gross_amount, discount_amount, taxable_amount,
                    cgst_amount, sgst_amount, igst_amount, cess_amount,
                    round_off, net_amount, amount_paid, balance_due, payment_method
                ) VALUES (
                    1, 1, 1, 1, 'BAD-1', '2026-09-15', 'COMPLETED', 'INTRASTATE',
                    299.00, 50.00, 253.39, 22.80, 22.80, 0.00, 0.00,
                    0.00, 249.00, 249.00, 0.00, 'CASH'
                )
                """
            )
        )


def test_database_rejects_mixed_intrastate_and_interstate_tax(
    db_session: scoped_session[Session],
) -> None:
    with pytest.raises(IntegrityError, match="ck_sales_tax_mode"):
        db_session.execute(
            text(
                """
                INSERT INTO sales (
                    company_id, branch_id, terminal_id, cashier_id,
                    invoice_number, business_date, sale_status, supply_type,
                    gross_amount, discount_amount, taxable_amount,
                    cgst_amount, sgst_amount, igst_amount, cess_amount,
                    round_off, net_amount, amount_paid, balance_due, payment_method
                ) VALUES (
                    1, 1, 1, 1, 'BAD-TAX-MODE', '2026-09-15', 'COMPLETED', 'INTERSTATE',
                    128.00, 0.00, 100.00, 5.00, 5.00, 18.00, 0.00,
                    0.00, 128.00, 128.00, 0.00, 'CASH'
                )
                """
            )
        )


def test_p0_3_database_rejects_non_positive_sale_quantity(
    db_session: scoped_session[Session],
) -> None:
    with pytest.raises(IntegrityError, match="ck_sale_items_qty"):
        db_session.execute(
            text(
                """
                INSERT INTO sale_items (
                    company_id, sale_id, product_id, line_number, quantity,
                    unit_price, gross_amount, discount_amount, taxable_amount,
                    tax_rate, cgst_rate, sgst_rate, igst_rate, cess_rate,
                    cgst_amount, sgst_amount, igst_amount, cess_amount, total_amount
                ) VALUES (
                    1, 1, 1, 1, 0.000,
                    100.00, 100.00, 0.00, 100.00,
                    0.00, 0.00, 0.00, 0.00, 0.00,
                    0.00, 0.00, 0.00, 0.00, 100.00
                )
                """
            )
        )


def test_model_repr_never_exposes_money_or_pii() -> None:
    product = Product(name="Sensitive Product", selling_price="999.99")  # type: ignore[arg-type]
    user = User(email="person@example.test", password_hash="secret-hash")
    sale = Sale(invoice_number="INV-SECRET", net_amount="999.99")  # type: ignore[arg-type]
    rendered = " ".join((repr(product), repr(user), repr(sale)))
    for secret in (
        "Sensitive Product",
        "999.99",
        "person@example.test",
        "secret-hash",
        "INV-SECRET",
    ):
        assert secret not in rendered


def test_required_str_enums_exist() -> None:
    for name in (
        "PaymentMethod",
        "SaleStatus",
        "SupplyType",
        "LedgerTxnType",
        "ShiftStatus",
        "DocType",
        "ReturnReason",
    ):
        enum_type = getattr(enums, name)
        assert issubclass(enum_type, StrEnum)
        assert list(enum_type)


def test_required_domain_events_are_frozen_dataclasses() -> None:
    for name in ("SaleCompleted", "StockDepleted", "ShiftClosed", "PriceOverridden"):
        event_type = getattr(events, name)
        assert is_dataclass(event_type)
        assert event_type.__dataclass_params__.frozen is True


def test_non_test_financial_sources_do_not_call_float() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "vglpos"
    offenders = [
        path for path in root.rglob("*.py") if "float(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_schema_was_created_in_test_database(db_session: scoped_session[Session]) -> None:
    assert set(inspect(db_session.bind).get_table_names()) >= EXPECTED_TABLES
