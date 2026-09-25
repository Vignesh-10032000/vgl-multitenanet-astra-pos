"""Thin batch, count, transfer, replenishment, and valuation API routes."""

from __future__ import annotations

from flask import Blueprint, Response
from sqlalchemy.orm import Session

from vglpos.api.v1.context import counter_context
from vglpos.api.v1.http import model_response, parse_body, parse_query
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.inventory_depth import (
    CountSheetCreateRequest,
    NearExpiryListResponse,
    NearExpiryQuery,
    NearExpiryResponse,
    ReorderListResponse,
    ReorderQuery,
    ReorderResponse,
    StockAuditResponse,
    StockCountRequest,
    StockTransferResponse,
    StockValueListResponse,
    StockValueResponse,
    TransferCreateRequest,
    VariantCreateRequest,
    VariantResponse,
)
from vglpos.extensions import db
from vglpos.security.decorators import require_permission
from vglpos.services.inventory_depth_service import (
    CreateTransferCommand,
    InventoryDepthService,
    StockCountLineCommand,
    TransferLineCommand,
    VariantCommand,
)
from vglpos.utils.money import ZERO, money

inventory_depth_bp = Blueprint("inventory_depth", __name__, url_prefix="/api/v1/inventory")


@inventory_depth_bp.post("/variants")
@require_permission("product.create")
@idempotent
@documented(
    summary="Create a product variant",
    request_model=VariantCreateRequest,
    response_model=VariantResponse,
    success_status=201,
)
def create_variant() -> tuple[Response, int]:
    body = parse_body(VariantCreateRequest)
    context = counter_context()
    command = VariantCommand(
        company_id=context.company_id,
        parent_product_id=body.parent_product_id,
        sku=body.sku,
        name=body.name,
        selling_price=body.selling_price,
        mrp=body.mrp,
        user_id=context.user_id,
        barcode=body.barcode,
        size=body.size,
        colour=body.colour,
        style=body.style,
    )
    with Session(db.engine) as session:
        variant = InventoryDepthService(session, context.company_id).create_variant(command)
        return model_response(VariantResponse.model_validate(variant), status=201)


@inventory_depth_bp.get("/near-expiry")
@require_permission("stock.view")
@documented(
    summary="List expired and near-expiry batches",
    query_model=NearExpiryQuery,
    response_model=NearExpiryListResponse,
)
def near_expiry() -> tuple[Response, int]:
    query = parse_query(NearExpiryQuery)
    context = counter_context()
    with Session(db.engine) as session:
        rows = InventoryDepthService(session, context.company_id).near_expiry(
            branch_id=context.branch_id, on_date=query.on_date, days=query.days
        )
        return model_response(
            NearExpiryListResponse(items=[NearExpiryResponse.model_validate(row) for row in rows])
        )


@inventory_depth_bp.post("/audits")
@require_permission("stock.audit")
@idempotent
@documented(
    summary="Generate a physical stock count sheet",
    request_model=CountSheetCreateRequest,
    response_model=StockAuditResponse,
    success_status=201,
)
def generate_count_sheet() -> tuple[Response, int]:
    body = parse_body(CountSheetCreateRequest)
    context = counter_context()
    with Session(db.engine) as session:
        audit = InventoryDepthService(session, context.company_id).generate_count_sheet(
            branch_id=context.branch_id,
            user_id=context.user_id,
            product_ids=body.product_ids,
        )
        return model_response(StockAuditResponse.model_validate(audit), status=201)


@inventory_depth_bp.put("/audits/<int:audit_id>/counts")
@require_permission("stock.audit")
@idempotent
@documented(
    summary="Enter a complete physical count",
    request_model=StockCountRequest,
    response_model=StockAuditResponse,
)
def enter_counts(audit_id: int) -> tuple[Response, int]:
    body = parse_body(StockCountRequest)
    context = counter_context()
    lines = [
        StockCountLineCommand(line.stock_audit_item_id, line.counted_quantity, line.reason)
        for line in body.lines
    ]
    with Session(db.engine) as session:
        audit = InventoryDepthService(session, context.company_id).enter_counts(
            stock_audit_id=audit_id, user_id=context.user_id, lines=lines
        )
        return model_response(StockAuditResponse.model_validate(audit))


@inventory_depth_bp.post("/audits/<int:audit_id>/post")
@require_permission("stock.audit")
@idempotent
@documented(summary="Post stock-count variances", response_model=StockAuditResponse)
def post_count(audit_id: int) -> tuple[Response, int]:
    context = counter_context()
    with Session(db.engine) as session:
        audit = InventoryDepthService(session, context.company_id).post_count(
            stock_audit_id=audit_id, user_id=context.user_id
        )
        return model_response(StockAuditResponse.model_validate(audit))


@inventory_depth_bp.post("/transfers")
@require_permission("stock.transfer")
@idempotent
@documented(
    summary="Create a draft inter-branch transfer",
    request_model=TransferCreateRequest,
    response_model=StockTransferResponse,
    success_status=201,
)
def create_transfer() -> tuple[Response, int]:
    body = parse_body(TransferCreateRequest)
    context = counter_context()
    command = CreateTransferCommand(
        company_id=context.company_id,
        source_branch_id=context.branch_id,
        destination_branch_id=body.destination_branch_id,
        terminal_id=context.terminal_id,
        user_id=context.user_id,
        transfer_date=body.transfer_date,
        notes=body.notes,
        lines=[
            TransferLineCommand(line.product_id, line.quantity, line.source_batch_id)
            for line in body.lines
        ],
    )
    with Session(db.engine) as session:
        transfer = InventoryDepthService(session, context.company_id).create_transfer(command)
        return model_response(StockTransferResponse.model_validate(transfer), status=201)


@inventory_depth_bp.post("/transfers/<int:transfer_id>/dispatch")
@require_permission("stock.transfer")
@idempotent
@documented(summary="Dispatch a draft stock transfer", response_model=StockTransferResponse)
def dispatch_transfer(transfer_id: int) -> tuple[Response, int]:
    context = counter_context()
    with Session(db.engine) as session:
        transfer = InventoryDepthService(session, context.company_id).dispatch_transfer(
            transfer_id=transfer_id, user_id=context.user_id
        )
        return model_response(StockTransferResponse.model_validate(transfer))


@inventory_depth_bp.post("/transfers/<int:transfer_id>/receive")
@require_permission("stock.transfer")
@idempotent
@documented(summary="Receive an in-transit stock transfer", response_model=StockTransferResponse)
def receive_transfer(transfer_id: int) -> tuple[Response, int]:
    context = counter_context()
    with Session(db.engine) as session:
        transfer = InventoryDepthService(session, context.company_id).receive_transfer(
            transfer_id=transfer_id, user_id=context.user_id
        )
        return model_response(StockTransferResponse.model_validate(transfer))


@inventory_depth_bp.get("/reorder-suggestions")
@require_permission("stock.reorder")
@documented(
    summary="Get lead-time and velocity based reorder suggestions",
    query_model=ReorderQuery,
    response_model=ReorderListResponse,
)
def reorder_suggestions() -> tuple[Response, int]:
    query = parse_query(ReorderQuery)
    context = counter_context()
    with Session(db.engine) as session:
        rows = InventoryDepthService(session, context.company_id).reorder_suggestions(
            branch_id=context.branch_id, as_of=query.as_of, sales_days=query.sales_days
        )
        return model_response(
            ReorderListResponse(items=[ReorderResponse.model_validate(row) for row in rows])
        )


@inventory_depth_bp.get("/valuation")
@require_permission("stock.view", "report.view", require_all=True)
@documented(summary="Value branch stock at cost and retail", response_model=StockValueListResponse)
def stock_valuation() -> tuple[Response, int]:
    context = counter_context()
    with Session(db.engine) as session:
        rows = InventoryDepthService(session, context.company_id).stock_value(
            branch_id=context.branch_id
        )
        return model_response(
            StockValueListResponse(
                items=[StockValueResponse.model_validate(row) for row in rows],
                total_cost_value=money(sum((row.cost_value for row in rows), ZERO)),
                total_retail_value=money(sum((row.retail_value for row in rows), ZERO)),
            )
        )
