"""Durable asynchronous report-job and artifact-boundary tests."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError
from vglpos.services.report_job_service import ReportJobService

from .conftest import ServiceContext, seed_service_context


def test_report_job_generates_a_tenant_scoped_downloadable_artifact(
    service_session: Session,
    service_context: ServiceContext,
    tmp_path: Path,
) -> None:
    service_context.company.gstin = "33AAAAA0000A1Z5"
    service_session.commit()
    service = ReportJobService(service_session, service_context.company.id)
    job = service.create(
        requested_by=service_context.cashier.id,
        report_name="gstr1",
        output_format="json",
        parameters={
            "start_date": date(2026, 8, 1).isoformat(),
            "end_date": date(2026, 8, 31).isoformat(),
            "branch_id": service_context.branch.id,
        },
    )

    completed = service.process(job.id, str(tmp_path))
    artifact, content_type = service.artifact(job.id, str(tmp_path))

    assert completed.status == "COMPLETED"
    assert completed.completed_at is not None
    assert artifact.parent == tmp_path.resolve()
    assert artifact.read_bytes().startswith(b'{\n  "gstin": "33AAAAA0000A1Z5"')
    assert content_type == "application/json"
    with pytest.raises(ConflictError, match="pending"):
        service.process(job.id, str(tmp_path))

    other = seed_service_context(service_session, company_name="Other Report Tenant")
    with pytest.raises(EntityNotFoundError):
        ReportJobService(service_session, other.company.id).get(job.id)


def test_report_job_validation_rejects_unknown_reports_formats_and_parameters(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = ReportJobService(service_session, service_context.company.id)
    with pytest.raises(ValidationError, match="Unsupported report"):
        service.create(
            requested_by=service_context.cashier.id,
            report_name="NOT_A_REPORT",
            output_format="JSON",
            parameters={},
        )
    with pytest.raises(ValidationError, match="does not support"):
        service.create(
            requested_by=service_context.cashier.id,
            report_name="GSTR3B",
            output_format="XLSX",
            parameters={"start_date": "2026-08-01", "end_date": "2026-08-31"},
        )
    with pytest.raises(ValidationError, match="ISO date"):
        service.create(
            requested_by=service_context.cashier.id,
            report_name="GSTR3B",
            output_format="JSON",
            parameters={"start_date": "not-a-date", "end_date": "2026-08-31"},
        )


def test_report_job_persists_and_logs_generation_failure(
    service_session: Session,
    service_context: ServiceContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service_context.company.gstin = "33AAAAA0000A1Z5"
    service_session.commit()
    service = ReportJobService(service_session, service_context.company.id)
    job = service.create(
        requested_by=service_context.cashier.id,
        report_name="GSTR3B",
        output_format="JSON",
        parameters={"start_date": "2026-08-01", "end_date": "2026-08-31"},
    )

    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(RuntimeError, match="REPORT_ARTIFACT_DIR"),
    ):
        service.process(job.id, "")

    failed = service.get(job.id)
    assert failed.status == "FAILED"
    assert failed.completed_at is not None
    assert failed.error_message == "REPORT_ARTIFACT_DIR is not configured."
    assert "Report artifact generation failed." in caplog.text
