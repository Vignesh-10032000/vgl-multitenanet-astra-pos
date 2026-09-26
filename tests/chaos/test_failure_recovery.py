"""Deterministic failure injection for checkout and report recovery paths."""

from __future__ import annotations

import errno
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from tests.integration.conftest import ServiceContext, open_service_shift

from vglpos.domain.models import Sale
from vglpos.services.checkout_service import (
    CheckoutCommand,
    CheckoutLineCommand,
    CheckoutService,
    PaymentCommand,
)
from vglpos.services.exceptions import CheckoutError
from vglpos.services.report_job_service import ReportJobService


def test_database_loss_mid_checkout_rolls_back_everything(
    service_session: Session,
    service_context: ServiceContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    open_service_shift(service_session, service_context)
    original_commit = service_session.commit

    def unavailable() -> None:
        raise OperationalError("COMMIT", {}, ConnectionError("database disconnected"))

    monkeypatch.setattr(service_session, "commit", unavailable)
    command = CheckoutCommand(
        company_id=service_context.company.id,
        branch_id=service_context.branch.id,
        terminal_id=service_context.terminal.id,
        cashier_id=service_context.cashier.id,
        lines=[CheckoutLineCommand(service_context.product.id, "1")],
        payments=[PaymentCommand("CASH", "118.00")],
    )
    with pytest.raises(CheckoutError, match="no sale was committed"):
        CheckoutService(service_session).checkout(command)
    monkeypatch.setattr(service_session, "commit", original_commit)
    assert service_session.scalar(select(func.count()).select_from(Sale)) == 0


def test_full_disk_marks_report_failed_for_operator_retry(
    service_session: Session,
    service_context: ServiceContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_context.company.gstin = "33AAAAA0000A1Z5"
    service_session.commit()
    service = ReportJobService(service_session, service_context.company.id)
    job = service.create(
        requested_by=service_context.cashier.id,
        report_name="GSTR3B",
        output_format="JSON",
        parameters={
            "start_date": date(2026, 8, 1).isoformat(),
            "end_date": date(2026, 8, 31).isoformat(),
        },
    )

    def disk_full(_self: Path, _data: bytes) -> int:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(Path, "write_bytes", disk_full)
    with pytest.raises(OSError) as exc_info:
        service.process(job.id, str(tmp_path))
    assert exc_info.value.errno == errno.ENOSPC
    assert service.get(job.id).status == "FAILED"
