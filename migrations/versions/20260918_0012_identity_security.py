"""Add Phase 2 identity and audit security fields.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _create_audit_immutability() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_audit_log_mutation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_log is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_audit_log_append_only
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation()
            """
        )
        return
    op.execute(
        """
        CREATE TRIGGER trg_audit_log_no_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_log_no_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only');
        END
        """
    )


def _drop_audit_immutability() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER trg_audit_log_append_only ON audit_log")
        op.execute("DROP FUNCTION reject_audit_log_mutation()")
        return
    op.execute("DROP TRIGGER trg_audit_log_no_update")
    op.execute("DROP TRIGGER trg_audit_log_no_delete")


def upgrade() -> None:
    """Add tenant discovery, hardened credentials, limits, and audit context."""
    op.add_column("companies", sa.Column("login_code", sa.String(50), nullable=True))
    op.create_index(
        "uq_companies_login_code",
        "companies",
        ["login_code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND login_code IS NOT NULL"),
        sqlite_where=sa.text("deleted_at IS NULL AND login_code IS NOT NULL"),
    )
    op.add_column("users", sa.Column("pin_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("mfa_secret", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "roles",
        sa.Column(
            "max_discount_percent",
            sa.Numeric(5, 2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_roles_max_discount_percent",
            "roles",
            "max_discount_percent >= 0 AND max_discount_percent <= 100",
        )
    else:
        with op.batch_alter_table("roles") as batch_op:
            batch_op.create_check_constraint(
                "ck_roles_max_discount_percent",
                "max_discount_percent >= 0 AND max_discount_percent <= 100",
            )
    op.add_column("audit_log", sa.Column("request_id", sa.String(36), nullable=True))
    _create_audit_immutability()


def downgrade() -> None:
    """Remove Phase 2 identity fields and append-only enforcement."""
    _drop_audit_immutability()
    op.drop_column("audit_log", "request_id")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("ck_roles_max_discount_percent", "roles", type_="check")
    else:
        with op.batch_alter_table("roles") as batch_op:
            batch_op.drop_constraint("ck_roles_max_discount_percent", type_="check")
    op.drop_column("roles", "max_discount_percent")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")
    op.drop_column("users", "pin_hash")
    op.drop_index("uq_companies_login_code", table_name="companies")
    op.drop_column("companies", "login_code")
