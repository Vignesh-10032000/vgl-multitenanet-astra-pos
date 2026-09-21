"""Atomic offline checkout synchronization endpoint."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, g
from sqlalchemy.orm import Session

from vglpos.api.v1.commands import checkout_command
from vglpos.api.v1.context import counter_context
from vglpos.api.v1.http import model_response, parse_body
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.sales import (
    OfflineBatchRequest,
    OfflineBatchResponse,
    OfflineBootstrapResponse,
    OfflineOperationResult,
    OfflinePushRequest,
    OfflinePushResponse,
)
from vglpos.api.v1.serializers import sale_response
from vglpos.extensions import db, limiter
from vglpos.security.decorators import require_permission
from vglpos.services.checkout_service import CheckoutService
from vglpos.services.sync_service import OfflineSyncService, SignedCheckoutOperation

sync_bp = Blueprint("sync", __name__, url_prefix="/api/v1/sync")


def _terminal_rate_key() -> str:
    return f"{g.company_id}:{g.terminal_id}"


def _sync_service(session: Session) -> OfflineSyncService:
    context = counter_context()
    return OfflineSyncService(
        session,
        company_id=context.company_id,
        branch_id=context.branch_id,
        terminal_id=context.terminal_id,
        signing_secret=str(current_app.config["OFFLINE_SYNC_SIGNING_SECRET"]),
    )


@sync_bp.get("/bootstrap")
@require_permission("sale.create")
@documented(
    summary="Provision terminal-bound offline checkout facts",
    response_model=OfflineBootstrapResponse,
)
def bootstrap() -> tuple[Response, int]:
    with Session(db.engine) as session:
        facts = _sync_service(session).bootstrap()
        return model_response(
            OfflineBootstrapResponse(
                terminal_code=facts.terminal_code,
                supplier_state=facts.supplier_state,
                signing_key=facts.signing_key,
            )
        )


@sync_bp.post("/batch")
@require_permission("sale.create")
@limiter.limit("120 per minute", key_func=_terminal_rate_key)
@idempotent
@documented(
    summary="Commit signed offline sales with per-operation results",
    request_model=OfflineBatchRequest,
    response_model=OfflineBatchResponse,
)
def batch() -> tuple[Response, int]:
    body = parse_body(OfflineBatchRequest)
    context = counter_context()
    operations = [
        SignedCheckoutOperation(
            uuid=operation.uuid,
            command=checkout_command(operation.sale, context),
            payload=operation.sale.model_dump(mode="json"),
            signature=operation.signature,
        )
        for operation in body.operations
    ]
    with Session(db.engine) as session:
        results = _sync_service(session).sync_batch(operations)
        return model_response(
            OfflineBatchResponse(
                results=[
                    OfflineOperationResult(
                        uuid=result.uuid,
                        status=result.status,
                        sale=sale_response(result.sale) if result.sale is not None else None,
                        error_type=result.error_type,
                        detail=result.detail,
                    )
                    for result in results
                ]
            )
        )


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
