"""Durable report jobs and artifact generation for non-blocking exports."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import ReportJob
from vglpos.security.audit import record_audit_event
from vglpos.services.exceptions import ConflictError, EntityNotFoundError, ValidationError
from vglpos.services.financial_report_service import FinancialReportService
from vglpos.services.inventory_depth_service import InventoryDepthService
from vglpos.services.report_export_service import ReportExportService
from vglpos.services.statutory_report_service import StatutoryReportService

type ReportParameter = str | int | bool | None

logger = logging.getLogger(__name__)

_FORMATS: dict[str, frozenset[str]] = {
    "GSTR1": frozenset({"JSON", "XLSX"}),
    "GSTR3B": frozenset({"JSON"}),
    "TALLY": frozenset({"XML"}),
    "RECONCILIATION": frozenset({"JSON"}),
    "HSN_REGISTER": frozenset({"JSON"}),
    "RATE_REGISTER": frozenset({"JSON"}),
    "GROSS_MARGIN": frozenset({"JSON"}),
    "DAY_BOOK": frozenset({"JSON"}),
    "CASH_BOOK": frozenset({"JSON"}),
    "CUSTOMER_AGEING": frozenset({"JSON"}),
    "SUPPLIER_AGEING": frozenset({"JSON"}),
    "SALES_COMPARISON": frozenset({"JSON"}),
    "HOURLY_SALES": frozenset({"JSON"}),
    "STOCK_VALUATION": frozenset({"JSON"}),
}

_EXTENSIONS = {"JSON": "json", "XLSX": "xlsx", "XML": "xml"}
_CONTENT_TYPES = {
    "JSON": "application/json",
    "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "XML": "application/xml",
}


class ReportJobService:
    """Validate, execute, and securely resolve tenant-scoped report artifacts."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def create(
        self,
        *,
        requested_by: int,
        report_name: str,
        output_format: str,
        parameters: dict[str, ReportParameter],
    ) -> ReportJob:
        """Persist a validated request before it is handed to Celery."""
        name = report_name.strip().upper()
        output = output_format.strip().upper()
        if not requested_by:
            raise ValidationError("Report requester is required.")
        if name not in _FORMATS:
            raise ValidationError(f"Unsupported report name: {name or '(blank)'}.")
        if output not in _FORMATS[name]:
            raise ValidationError(f"{name} does not support {output or '(blank)'} output.")
        self._validate_parameters(name, parameters)
        job = ReportJob(
            company_id=self.company_id,
            requested_by=requested_by,
            report_name=name,
            output_format=output,
            parameters=dict(parameters),
            status="PENDING",
            created_by=requested_by,
        )
        self.session.add(job)
        self.session.flush()
        record_audit_event(
            self.session,
            company_id=self.company_id,
            user_id=requested_by,
            action="REQUEST",
            entity_type="ReportJob",
            entity_id=job.id,
            new_values={"report_name": name, "output_format": output},
        )
        self.session.commit()
        self.session.refresh(job)
        return job

    def get(self, job_id: int) -> ReportJob:
        job = self.session.scalar(
            select(ReportJob).where(
                ReportJob.id == job_id,
                ReportJob.company_id == self.company_id,
                ReportJob.deleted_at.is_(None),
            )
        )
        if job is None:
            raise EntityNotFoundError("Report job was not found.")
        return job

    def process(self, job_id: int, artifact_directory: str) -> ReportJob:
        """Run one claimed job and atomically publish its artifact."""
        job = self.get(job_id)
        if job.status != "PENDING":
            raise ConflictError("Only a pending report job can be processed.")
        job.status = "RUNNING"
        job.error_message = None
        self.session.commit()
        try:
            artifact = self._generate(job)
            directory = self._artifact_root(artifact_directory)
            directory.mkdir(parents=True, exist_ok=True)
            extension = _EXTENSIONS[job.output_format]
            filename = f"report-{job.id}-{uuid4().hex}.{extension}"
            path = directory / filename
            temporary = directory / f".{filename}.tmp"
            temporary.write_bytes(artifact)
            os.replace(temporary, path)
            job.artifact_path = str(path)
            job.status = "COMPLETED"
            job.completed_at = datetime.now(UTC)
            record_audit_event(
                self.session,
                company_id=self.company_id,
                user_id=job.requested_by,
                action="EXPORT",
                entity_type="ReportJob",
                entity_id=job.id,
                new_values={"report_name": job.report_name, "format": job.output_format},
            )
            self.session.commit()
            self.session.refresh(job)
            return job
        except Exception as exc:
            logger.exception(
                "Report artifact generation failed.",
                extra={"company_id": self.company_id, "report_job_id": job_id},
            )
            self.session.rollback()
            failed = self.get(job_id)
            failed.status = "FAILED"
            failed.error_message = str(exc)[:2000]
            failed.completed_at = datetime.now(UTC)
            self.session.commit()
            raise

    def artifact(self, job_id: int, artifact_directory: str) -> tuple[Path, str]:
        """Return a completed artifact only when it remains below the configured root."""
        job = self.get(job_id)
        if job.status != "COMPLETED" or not job.artifact_path:
            raise ConflictError("Report artifact is not ready for download.")
        root = self._artifact_root(artifact_directory)
        path = Path(job.artifact_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise EntityNotFoundError("Report artifact was not found.")
        return path, _CONTENT_TYPES[job.output_format]

    def _generate(self, job: ReportJob) -> bytes:
        params = job.parameters
        branch_id = self._optional_int(params, "branch_id")
        statutory = StatutoryReportService(self.session, self.company_id)
        exporter = ReportExportService(self.session, self.company_id)
        if job.report_name == "GSTR1":
            report = statutory.gstr1(
                self._date(params, "start_date"),
                self._date(params, "end_date"),
                branch_id=branch_id,
            )
            if job.output_format == "XLSX":
                return exporter.gstr1_offline_xlsx(report)
            return exporter.gstr1_json(report)
        if job.report_name == "TALLY":
            return exporter.tally_xml(
                self._date(params, "start_date"),
                self._date(params, "end_date"),
                branch_id=branch_id,
            )
        if job.report_name == "GSTR3B":
            value: object = statutory.gstr3b(
                self._date(params, "start_date"),
                self._date(params, "end_date"),
                branch_id=branch_id,
            )
        elif job.report_name == "RECONCILIATION":
            value = statutory.reconciliation(
                self._date(params, "start_date"),
                self._date(params, "end_date"),
                branch_id=branch_id,
            )
        elif job.report_name == "HSN_REGISTER":
            value = statutory.hsn_register(
                self._date(params, "start_date"),
                self._date(params, "end_date"),
                branch_id=branch_id,
            )
        elif job.report_name == "RATE_REGISTER":
            value = statutory.rate_register(
                self._date(params, "start_date"),
                self._date(params, "end_date"),
                branch_id=branch_id,
            )
        elif job.report_name == "STOCK_VALUATION":
            if branch_id is None:
                raise ValidationError("branch_id is required for stock valuation.")
            value = InventoryDepthService(self.session, self.company_id).stock_value(
                branch_id=branch_id
            )
        else:
            value = self._financial_report(job.report_name, params, branch_id)
        return json.dumps(
            value,
            default=self._json_default,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

    def _financial_report(
        self,
        name: str,
        params: dict[str, ReportParameter],
        branch_id: int | None,
    ) -> object:
        service = FinancialReportService(self.session, self.company_id)
        if name == "CUSTOMER_AGEING":
            return service.customer_ageing(as_of=self._date(params, "as_of"))
        if name == "SUPPLIER_AGEING":
            return service.supplier_ageing(as_of=self._date(params, "as_of"))
        start_date = self._date(params, "start_date")
        end_date = self._date(params, "end_date")
        if name == "GROSS_MARGIN":
            return service.gross_margin(
                start_date,
                end_date,
                dimension=self._string(params, "dimension"),
                branch_id=branch_id,
            )
        if name == "DAY_BOOK":
            return service.day_book(start_date, end_date, branch_id=branch_id)
        if name == "CASH_BOOK":
            return service.cash_book(start_date, end_date, branch_id=branch_id)
        if name == "HOURLY_SALES":
            return service.hourly_sales(start_date, end_date, branch_id=branch_id)
        if name == "SALES_COMPARISON":
            return service.sales_comparison(
                start_date,
                end_date,
                self._date(params, "previous_start"),
                self._date(params, "previous_end"),
                branch_id=branch_id,
            )
        raise ValidationError(f"Unsupported financial report: {name}.")

    @classmethod
    def _validate_parameters(cls, name: str, parameters: dict[str, ReportParameter]) -> None:
        if name in {"CUSTOMER_AGEING", "SUPPLIER_AGEING"}:
            cls._date(parameters, "as_of")
            return
        if name == "STOCK_VALUATION":
            if cls._optional_int(parameters, "branch_id") is None:
                raise ValidationError("branch_id is required for stock valuation.")
            return
        start = cls._date(parameters, "start_date")
        end = cls._date(parameters, "end_date")
        if start > end:
            raise ValidationError("Report start date cannot be after end date.")
        if name == "GROSS_MARGIN":
            cls._string(parameters, "dimension")
        if name == "SALES_COMPARISON":
            previous_start = cls._date(parameters, "previous_start")
            previous_end = cls._date(parameters, "previous_end")
            if previous_start > previous_end:
                raise ValidationError("Previous period start cannot be after its end.")

    @staticmethod
    def _date(parameters: dict[str, ReportParameter], name: str) -> date:
        value = parameters.get(name)
        if not isinstance(value, str):
            raise ValidationError(f"{name} is required in ISO date format.")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError(f"{name} must use ISO date format.") from exc

    @staticmethod
    def _string(parameters: dict[str, ReportParameter], name: str) -> str:
        value = parameters.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{name} is required.")
        return value.strip()

    @staticmethod
    def _optional_int(parameters: dict[str, ReportParameter], name: str) -> int | None:
        value = parameters.get(name)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValidationError(f"{name} must be a positive integer.")
        return value

    @staticmethod
    def _json_default(value: object) -> object:
        if is_dataclass(value) and not isinstance(value, type):
            return asdict(value)
        if isinstance(value, (date, datetime, Decimal)):
            return str(value)
        raise TypeError(f"Unsupported report value: {type(value).__name__}.")

    @staticmethod
    def _artifact_root(value: str) -> Path:
        if not value.strip():
            raise RuntimeError("REPORT_ARTIFACT_DIR is not configured.")
        return Path(value).resolve()
