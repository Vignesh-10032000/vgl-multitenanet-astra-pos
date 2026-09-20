"""Operator-facing consistency maintenance commands."""

from __future__ import annotations

import click
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import Company
from vglpos.extensions import db
from vglpos.services.customer_reconciliation import CustomerCounterReconciliationService


@click.command("reconcile-customer-counters")
@click.option("--company-id", type=click.IntRange(min=1), default=None)
@click.option("--check-only", is_flag=True, help="Report drift without updating counters.")
@with_appcontext
def reconcile_customer_counters(company_id: int | None, check_only: bool) -> None:
    """Recompute customer order and spend counters from completed sales."""
    with Session(db.engine) as session:
        if company_id is None:
            company_ids = tuple(
                session.scalars(select(Company.id).where(Company.deleted_at.is_(None)))
            )
        else:
            exists = session.scalar(
                select(Company.id).where(
                    Company.id == company_id,
                    Company.deleted_at.is_(None),
                )
            )
            if exists is None:
                raise click.ClickException(f"Company {company_id} does not exist.")
            company_ids = (company_id,)

        total_drift = 0
        for value in company_ids:
            rows = CustomerCounterReconciliationService(session, value).reconcile(
                apply=not check_only
            )
            total_drift += len(rows)
            for row in rows:
                click.echo(
                    f"company={value} customer={row.customer_id} "
                    f"orders={row.stored_total_orders}->{row.expected_total_orders} "
                    f"spent={row.stored_total_spent}->{row.expected_total_spent}"
                )
    action = "reported" if check_only else "repaired"
    click.echo(f"Customer counter reconciliation complete: {total_drift} drift row(s) {action}.")
