"""Atomic offline checkout synchronization endpoint."""

from __future__ import annotations

from flask import Blueprint, Response, g
from sqlalchemy.orm import Session

from vglpos.api.v1.commands import checkout_command
from vglpos.api.v1.context import counter_context
from vglpos.api.v1.http import model_response, parse_body
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.sales import OfflinePushRequest, OfflinePushResponse
from vglpos.api.v1.serializers import sale_response
from vglpos.extensions import db, limiter
from vglpos.security.decorators import require_permission
from vglpos.services.checkout_service import CheckoutService

sync_bp = Blueprint("sync", __name__, url_prefix="/api/v1/sync")


def _terminal_rate_key() -> str:
    return f"{g.company_id}:{g.terminal_id}"


@sync_bp.post("/offline-push")
@require_permission("sale.create")
@limiter.limit("120 per minute", key_func=_terminal_rate_key)
@idempotent
@documented(
    summary="Atomically commit an offline sale batch",
    request_model=OfflinePushRequest,
    response_model=OfflinePushResponse,
    success_status=201,
)
def offline_push() -> tuple[Response, int]:
    body = parse_body(OfflinePushRequest)
    context = counter_context()
    commands = [checkout_command(sale, context) for sale in body.sales]
    with Session(db.engine) as session:
        sales = CheckoutService(session).checkout_batch(commands)
        response = OfflinePushResponse(sales=[sale_response(sale) for sale in sales])
        return model_response(response, status=201)
