"""Celery entry point for durable report artifact generation."""

from __future__ import annotations

from flask import current_app
from sqlalchemy.orm import Session

from vglpos.extensions import celery, db
from vglpos.services.report_job_service import ReportJobService


@celery.task(name="vglpos.generate_report_artifact")
def generate_report_artifact(*, company_id: int, job_id: int) -> dict[str, int | str]:
    """Generate one tenant-bound artifact and persist its terminal job state."""
    with Session(db.engine) as session:
        job = ReportJobService(session, company_id).process(
            job_id, str(current_app.config["REPORT_ARTIFACT_DIR"])
        )
        return {"job_id": job.id, "status": job.status}
