"""Phase 1B domain model validation tests.

Tests cover:
- Multi-tenancy integrity: every tenant model requires a non-nullable company_id FK
- Zero-Float rule: monetary, tax, and inventory columns use explicit Numeric precision
- Append-only stock ledger: strictly no updated_at or is_edited columns
- Model schema creation and relation navigation
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Float, Numeric, inspect
from sqlalchemy.orm import Session, scoped_session

from vglpos.domain.models import (
    Branch,
    Company,
    Product,
    Register,
    StockLedgerEntry,
    StockMovementType,
    TaxRate,
)
from vglpos.extensions import db


def test_zero_float_rule_across_all_models() -> None:
    """Verify that NO column across any model uses Float or sa.Float."""
    models = [Company, Branch, Register, Product, StockLedgerEntry, TaxRate]
    for model in models:
        mapper = inspect(model)
        for col in mapper.columns:
            assert not isinstance(col.type, Float), (
                f"Column {model.__tablename__}.{col.key} violates Zero Float rule by using Float!"
            )


def test_strict_tenancy_company_id_fk_present() -> None:
    """Verify all tenant-scoped tables carry a non-nullable company_id FK."""
    tenant_models = [Branch, Register, Product, StockLedgerEntry, TaxRate]
    for model in tenant_models:
        mapper = inspect(model)
        company_id_col = mapper.columns.get("company_id")
        assert company_id_col is not None, f"Model {model.__tablename__} is missing company_id!"
        assert not company_id_col.nullable, (
            f"{model.__tablename__}.company_id must be non-nullable!"
        )
        fk_targets = [fk.target_fullname for fk in company_id_col.foreign_keys]
        assert "companies.id" in fk_targets, (
            f"{model.__tablename__}.company_id must point to companies.id!"
        )


def test_stock_ledger_is_strictly_append_only() -> None:
    """Verify StockLedgerEntry has no update-style columns (no updated_at, no is_edited)."""
    mapper = inspect(StockLedgerEntry)
    col_names = [col.key for col in mapper.columns]
    assert "updated_at" not in col_names, "StockLedgerEntry must NOT have updated_at (append-only)!"
    assert "is_edited" not in col_names, "StockLedgerEntry must NOT have is_edited (append-only)!"
    assert "created_at" in col_names, "StockLedgerEntry must have movement timestamp created_at!"


def test_column_numeric_precisions() -> None:
    """Verify explicit precision and scale for currency, tax, and stock quantities."""
    # Product prices: Numeric(12, 2)
    prod_mapper = inspect(Product)
    base_price_type = prod_mapper.columns["base_price"].type
    assert isinstance(base_price_type, Numeric)
    assert base_price_type.precision == 12
    assert base_price_type.scale == 2

    mrp_type = prod_mapper.columns["mrp"].type
    assert isinstance(mrp_type, Numeric)
    assert mrp_type.precision == 12
    assert mrp_type.scale == 2

    # Stock quantity: Numeric(12, 3)
    stock_mapper = inspect(StockLedgerEntry)
    qty_type = stock_mapper.columns["quantity"].type
    assert isinstance(qty_type, Numeric)
    assert qty_type.precision == 12
    assert qty_type.scale == 3

    # Tax rates: Numeric(5, 2)
    tax_mapper = inspect(TaxRate)
    for rate_field in ["cgst_rate", "sgst_rate", "igst_rate"]:
        rate_type = tax_mapper.columns[rate_field].type
        assert isinstance(rate_type, Numeric)
        assert rate_type.precision == 5
        assert rate_type.scale == 2


def test_domain_models_persistence_and_relationships(db_session: scoped_session[Session]) -> None:
    """Create test records and verify foreign key traversal and decimal accuracy."""
    # Create tables in the test database for the session
    db.metadata.create_all(bind=db.engine)

    company = Company(
        name="Manickam Stores Pvt Ltd",
        gstin="33ABCDE1234F1Z5",
        city="Chennai",
        state="Tamil Nadu",
        state_code="33",
        contact_phone="+919876543210",
    )
    db_session.add(company)
    db_session.flush()

    assert company.id is not None
    assert company.is_active is True

    branch = Branch(
        company_id=company.id,
        name="T Nagar Branch",
        code="TNG01",
        city="Chennai",
        state="Tamil Nadu",
        state_code="33",
    )
    db_session.add(branch)
    db_session.flush()

    register = Register(
        company_id=company.id,
        branch_id=branch.id,
        name="Counter 1",
        code="REG01",
    )
    db_session.add(register)
    db_session.flush()

    product = Product(
        company_id=company.id,
        name="Ponni Boiled Rice 25kg",
        sku="RIC-PON-25",
        barcode="8901234567890",
        category="Grains",
        unit_of_measure="BAG",
        base_price=Decimal("1350.00"),
        mrp=Decimal("1500.00"),
        cost_price=Decimal("1200.00"),
        hsn_code="10063010",
    )
    db_session.add(product)
    db_session.flush()

    tax_rate = TaxRate(
        company_id=company.id,
        name="GST 5%",
        cgst_rate=Decimal("2.50"),
        sgst_rate=Decimal("2.50"),
        igst_rate=Decimal("5.00"),
        hsn_code_pattern="1006%",
        category="Food Grains",
        effective_from=date(2026, 1, 1),
    )
    db_session.add(tax_rate)
    db_session.flush()

    stock_entry = StockLedgerEntry(
        company_id=company.id,
        branch_id=branch.id,
        product_id=product.id,
        movement_type=StockMovementType.PURCHASE,
        quantity=Decimal("50.000"),
        reference_doc_id="GRN-2026-001",
        notes="Initial stock intake",
    )
    db_session.add(stock_entry)
    db_session.flush()

    # Relationship verification
    assert branch.company.name == "Manickam Stores Pvt Ltd"
    assert register.branch.name == "T Nagar Branch"
    assert register.company.id == company.id
    assert product.company.id == company.id
    assert stock_entry.product.name == "Ponni Boiled Rice 25kg"
    assert stock_entry.branch.code == "TNG01"
    assert stock_entry.quantity == Decimal("50.000")
    assert isinstance(product.base_price, Decimal)
