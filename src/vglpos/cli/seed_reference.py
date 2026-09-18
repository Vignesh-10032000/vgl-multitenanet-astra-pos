"""Idempotently seed statutory and RBAC reference data."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import click
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import Company, Permission, Role, RolePermission, TaxRate
from vglpos.domain.reference import STATE_CODES
from vglpos.extensions import db
from vglpos.security.permissions import PERMISSION_DEFINITIONS, STANDARD_ROLES

_PRE_GST_2_RATES: tuple[str, ...] = ("0", "5", "12", "18", "28")
_GST_2_RATES: tuple[str, ...] = ("0", "5", "18", "40")


def _split_rate(rate: Decimal) -> Decimal:
    """Split an intrastate slab exactly without binary floating point."""
    return rate / Decimal("2")


def _seed_permissions(session: Session) -> int:
    created = 0
    for definition in PERMISSION_DEFINITIONS:
        existing = session.scalar(select(Permission).where(Permission.code == definition.code))
        if existing is None:
            session.add(
                Permission(
                    code=definition.code,
                    description=definition.description,
                    category=definition.category,
                )
            )
            created += 1
    return created


def _seed_standard_roles(session: Session, company_id: int) -> int:
    permissions = {
        permission.code: permission
        for permission in session.scalars(select(Permission).where(Permission.deleted_at.is_(None)))
    }
    created = 0
    for definition in STANDARD_ROLES:
        role = session.scalar(
            select(Role).where(
                Role.company_id == company_id,
                Role.name == definition.name,
                Role.deleted_at.is_(None),
            )
        )
        if role is None:
            role = Role(
                company_id=company_id,
                name=definition.name,
                description=definition.description,
                is_system=True,
                max_discount_percent=definition.max_discount_percent,
            )
            session.add(role)
            session.flush()
            created += 1
        existing_ids = set(
            session.scalars(
                select(RolePermission.permission_id).where(
                    RolePermission.company_id == company_id,
                    RolePermission.role_id == role.id,
                    RolePermission.deleted_at.is_(None),
                )
            )
        )
        for code in definition.permissions:
            permission = permissions[code]
            if permission.id not in existing_ids:
                session.add(
                    RolePermission(
                        company_id=company_id,
                        role_id=role.id,
                        permission_id=permission.id,
                    )
                )
    return created


def _seed_company_rates(session: Session, company_id: int) -> int:
    created = 0
    schedules = (
        (_PRE_GST_2_RATES, date(2017, 7, 1), date(2025, 9, 21), "pre-GST-2.0"),
        (_GST_2_RATES, date(2025, 9, 22), None, "GST-2.0"),
    )
    for slabs, effective_from, effective_to, label in schedules:
        for slab in slabs:
            rate = Decimal(slab)
            name = f"GST {slab}% ({label})"
            existing = session.scalar(
                select(TaxRate).where(
                    TaxRate.company_id == company_id,
                    TaxRate.name == name,
                    TaxRate.effective_from == effective_from,
                    TaxRate.deleted_at.is_(None),
                )
            )
            if existing is None:
                session.add(
                    TaxRate(
                        company_id=company_id,
                        name=name,
                        rate=rate,
                        cgst_rate=_split_rate(rate),
                        sgst_rate=_split_rate(rate),
                        igst_rate=rate,
                        cess_rate=Decimal("0.00"),
                        effective_from=effective_from,
                        effective_to=effective_to,
                        is_active=effective_to is None,
                    )
                )
                created += 1
    return created


@click.command("seed-reference")
@click.option("--company-id", type=int, default=None, help="Seed rates for one company only.")
@with_appcontext
def seed_reference(company_id: int | None) -> None:
    """Seed permissions and dated GST slabs without inventing tenant data."""
    if len(STATE_CODES) != 37:
        raise click.ClickException("The statutory state-code catalogue must contain 37 entries.")

    with Session(db.engine) as session, session.begin():
        permission_count = _seed_permissions(session)
        if company_id is None:
            company_ids = list(
                session.scalars(select(Company.id).where(Company.deleted_at.is_(None)))
            )
        else:
            company_exists = session.scalar(
                select(Company.id).where(Company.id == company_id, Company.deleted_at.is_(None))
            )
            if company_exists is None:
                raise click.ClickException(f"Company {company_id} does not exist.")
            company_ids = [company_id]

        rate_count = sum(_seed_company_rates(session, value) for value in company_ids)
        role_count = sum(_seed_standard_roles(session, value) for value in company_ids)
    click.echo(
        f"Reference seed complete: {len(STATE_CODES)} state codes available; "
        f"{permission_count} permissions, {role_count} roles, and "
        f"{rate_count} GST rates inserted."
    )
