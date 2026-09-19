"""Thin cash-drawer shift API routes."""

from __future__ import annotations

from flask import Blueprint, Response
from sqlalchemy.orm import Session

from vglpos.api.v1.context import counter_context
from vglpos.api.v1.http import model_response, parse_body
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.shifts import (
    CashMovementRequest,
    CashMovementResponse,
    CloseShiftRequest,
    OpenShiftRequest,
    ShiftResponse,
)
from vglpos.api.v1.serializers import cash_movement_response, shift_response
from vglpos.extensions import db
from vglpos.security.decorators import require_permission
from vglpos.services.shift_service import (
    CashMovementCommand,
    CloseShiftCommand,
    OpenShiftCommand,
    ShiftService,
)

shifts_bp = Blueprint("shifts", __name__, url_prefix="/api/v1/shifts")


@shifts_bp.post("/open")
@require_permission("shift.open")
@idempotent
@documented(
    summary="Open a terminal shift",
    request_model=OpenShiftRequest,
    response_model=ShiftResponse,
    success_status=201,
)
def open_shift() -> tuple[Response, int]:
    body = parse_body(OpenShiftRequest)
    context = counter_context()
    command = OpenShiftCommand(
        context.company_id,
        context.branch_id,
        context.terminal_id,
        context.user_id,
        body.opening_cash,
        body.notes,
    )
    with Session(db.engine) as session:
        return model_response(shift_response(ShiftService(session).open_shift(command)), status=201)


@shifts_bp.post("/cash-movement")
@require_permission("cash.move")
@idempotent
@documented(
    summary="Record a cash movement",
    request_model=CashMovementRequest,
    response_model=CashMovementResponse,
    success_status=201,
)
def cash_movement() -> tuple[Response, int]:
    body = parse_body(CashMovementRequest)
    context = counter_context()
    command = CashMovementCommand(
        context.company_id,
        body.shift_id,
        body.movement_type,
        body.amount,
        body.reason,
        context.user_id,
        context.branch_id,
        context.terminal_id,
    )
    with Session(db.engine) as session:
        movement = ShiftService(session).record_cash_movement(command)
        return model_response(cash_movement_response(movement), status=201)


@shifts_bp.post("/close")
@require_permission("shift.close")
@idempotent
@documented(
    summary="Close a shift from a blind cash count",
    request_model=CloseShiftRequest,
    response_model=ShiftResponse,
)
def close_shift() -> tuple[Response, int]:
    body = parse_body(CloseShiftRequest)
    context = counter_context()
    command = CloseShiftCommand(
        context.company_id,
        body.shift_id,
        body.counted_cash,
        context.user_id,
        body.notes,
        context.branch_id,
        context.terminal_id,
    )
    with Session(db.engine) as session:
        return model_response(shift_response(ShiftService(session).close_shift(command)))
