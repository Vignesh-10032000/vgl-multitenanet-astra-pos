"""Gapless fiscal document number allocation."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from vglpos.domain.models import DocumentSeries, Terminal
from vglpos.services.exceptions import EntityNotFoundError, InvoiceNumberError, ValidationError
from vglpos.utils.gst import financial_year_code


class InvoiceNumberService:
    """Allocate numbers inside the transaction owned by a calling service."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def allocate(
        self,
        company_id: int,
        branch_id: int,
        terminal_id: int,
        doc_type: str,
        on_date: date,
    ) -> tuple[str, str]:
        """Lock and advance a series without committing, so rollback never burns a number."""
        if not company_id or not branch_id or not terminal_id:
            raise ValidationError("Company, branch, and terminal are required for numbering.")
        terminal_exists = self.session.scalar(
            select(Terminal.id).where(
                Terminal.id == terminal_id,
                Terminal.company_id == company_id,
                Terminal.branch_id == branch_id,
                Terminal.deleted_at.is_(None),
                Terminal.is_active.is_(True),
            )
        )
        if terminal_exists is None:
            raise EntityNotFoundError("Terminal was not found for the branch.")

        fy_code = financial_year_code(on_date)
        series = self.session.scalar(
            select(DocumentSeries)
            .where(
                DocumentSeries.company_id == company_id,
                DocumentSeries.branch_id == branch_id,
                DocumentSeries.doc_type == doc_type,
                DocumentSeries.financial_year == fy_code,
                DocumentSeries.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if series is None:
            raise InvoiceNumberError(
                f"No {doc_type} document series is configured for financial year {fy_code}."
            )

        next_number = series.current_number + 1
        document_no = f"{series.prefix}{next_number:06d}{series.suffix or ''}"
        if len(document_no) > 16:
            raise InvoiceNumberError("Fiscal document number cannot exceed 16 characters.")
        allocated_number = self.session.scalar(
            update(DocumentSeries)
            .where(
                DocumentSeries.id == series.id,
                DocumentSeries.company_id == company_id,
            )
            .values(current_number=DocumentSeries.current_number + 1)
            .returning(DocumentSeries.current_number)
        )
        if allocated_number is None:
            raise InvoiceNumberError("Fiscal document series could not be advanced.")
        document_no = f"{series.prefix}{allocated_number:06d}{series.suffix or ''}"
        if len(document_no) > 16:
            raise InvoiceNumberError("Fiscal document number cannot exceed 16 characters.")
        return document_no, fy_code
