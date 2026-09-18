"""Create users, roles, permissions, and assignment tables.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from vglpos.migration_schema import BIGINT, audit_columns, id_column, tenant_column

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the company-scoped identity and RBAC schema."""
    op.create_table(
        "users",
        id_column(),
        tenant_column(),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "failed_login_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        *audit_columns(),
    )
    op.create_index(
        "uq_users_company_username",
        "users",
        ["company_id", "username"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_users_company_email",
        "users",
        ["company_id", "email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("idx_users_company_id", "users", ["company_id"])

    op.create_table(
        "roles",
        id_column(),
        tenant_column(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *audit_columns(),
    )
    op.create_index(
        "uq_roles_company_name",
        "roles",
        ["company_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "permissions",
        id_column(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        *audit_columns(),
    )
    op.create_index(
        "uq_permissions_code",
        "permissions",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "role_permissions",
        id_column(),
        tenant_column(),
        sa.Column(
            "role_id",
            BIGINT,
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "permission_id",
            BIGINT,
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *audit_columns(),
    )
    op.create_index(
        "uq_role_permissions_pair",
        "role_permissions",
        ["role_id", "permission_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "user_roles",
        id_column(),
        tenant_column(),
        sa.Column(
            "user_id",
            BIGINT,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            BIGINT,
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            BIGINT,
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=True,
        ),
        *audit_columns(),
    )
    op.create_index(
        "uq_user_roles_pair",
        "user_roles",
        ["user_id", "role_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    for table_name in ("companies", "branches", "terminals"):
        for column_name in ("created_by", "updated_by", "deleted_by"):
            constraint_name = f"fk_{table_name}_{column_name}_users"
            if op.get_bind().dialect.name == "postgresql":
                op.create_foreign_key(
                    constraint_name,
                    table_name,
                    "users",
                    [column_name],
                    ["id"],
                    ondelete="RESTRICT",
                )
            else:
                with op.batch_alter_table(table_name) as batch_op:
                    batch_op.create_foreign_key(
                        constraint_name,
                        "users",
                        [column_name],
                        ["id"],
                        ondelete="RESTRICT",
                    )


def downgrade() -> None:
    """Remove RBAC and identity tables."""
    for table_name in ("companies", "branches", "terminals"):
        for column_name in ("created_by", "updated_by", "deleted_by"):
            constraint_name = f"fk_{table_name}_{column_name}_users"
            if op.get_bind().dialect.name == "postgresql":
                op.drop_constraint(
                    constraint_name,
                    table_name,
                    type_="foreignkey",
                )
            else:
                with op.batch_alter_table(table_name) as batch_op:
                    batch_op.drop_constraint(constraint_name, type_="foreignkey")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
