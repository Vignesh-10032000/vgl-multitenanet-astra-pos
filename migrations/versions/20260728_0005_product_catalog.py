"""Create product_catalog table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("barcode", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), server_default=sa.text("'PCS'"), nullable=False),
        sa.Column("base_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("mrp", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("cost_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("hsn_code", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name=op.f("fk_product_catalog_company_id_companies"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_catalog")),
    )
    op.create_index(op.f("ix_product_catalog_company_id"), "product_catalog", ["company_id"], unique=False)
    op.create_index(op.f("ix_product_catalog_name"), "product_catalog", ["name"], unique=False)
    op.create_index(op.f("ix_product_catalog_sku"), "product_catalog", ["sku"], unique=False)
    op.create_index(op.f("ix_product_catalog_barcode"), "product_catalog", ["barcode"], unique=False)
    op.create_index(op.f("ix_product_catalog_category"), "product_catalog", ["category"], unique=False)
    op.create_index(op.f("ix_product_catalog_hsn_code"), "product_catalog", ["hsn_code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_product_catalog_hsn_code"), table_name="product_catalog")
    op.drop_index(op.f("ix_product_catalog_category"), table_name="product_catalog")
    op.drop_index(op.f("ix_product_catalog_barcode"), table_name="product_catalog")
    op.drop_index(op.f("ix_product_catalog_sku"), table_name="product_catalog")
    op.drop_index(op.f("ix_product_catalog_name"), table_name="product_catalog")
    op.drop_index(op.f("ix_product_catalog_company_id"), table_name="product_catalog")
    op.drop_table("product_catalog")
