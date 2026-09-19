"""Thin tenant-scoped customer API routes."""

from __future__ import annotations

from flask import Blueprint, Response, g
from sqlalchemy.orm import Session

from vglpos.api.v1.http import model_response, parse_body, parse_query
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.customers import (
    CustomerCreateRequest,
    CustomerDetailResponse,
    CustomerPageResponse,
    CustomerQuery,
    CustomerResponse,
)
from vglpos.api.v1.serializers import customer_detail_response, customer_response
from vglpos.extensions import db
from vglpos.security.decorators import require_permission
from vglpos.services.customer_service import CreateCustomerCommand, CustomerService

customers_bp = Blueprint("customers", __name__, url_prefix="/api/v1/customers")


@customers_bp.get("")
@require_permission("customer.view")
@documented(
    summary="List and search customers",
    query_model=CustomerQuery,
    response_model=CustomerPageResponse,
)
def list_customers() -> tuple[Response, int]:
    query = parse_query(CustomerQuery)
    with Session(db.engine) as session:
        page = CustomerService(session, g.company_id, branch_id=g.branch_id).list_customers(
            cursor=query.cursor, limit=query.limit, query=query.q
        )
        response = CustomerPageResponse(
            items=[customer_response(item) for item in page.items], next_cursor=page.next_cursor
        )
        return model_response(response)


@customers_bp.post("")
@require_permission("customer.create")
@idempotent
@documented(
    summary="Create a customer",
    request_model=CustomerCreateRequest,
    response_model=CustomerResponse,
    success_status=201,
)
def create_customer() -> tuple[Response, int]:
    body = parse_body(CustomerCreateRequest)
    command = CreateCustomerCommand(company_id=g.company_id, user_id=g.user_id, **body.model_dump())
    with Session(db.engine) as session:
        customer = CustomerService(session, g.company_id, branch_id=g.branch_id).create_customer(
            command
        )
        return model_response(customer_response(customer), status=201)


@customers_bp.get("/<int:customer_id>")
@require_permission("customer.view")
@documented(summary="Get customer details and purchases", response_model=CustomerDetailResponse)
def get_customer(customer_id: int) -> tuple[Response, int]:
    with Session(db.engine) as session:
        detail = CustomerService(session, g.company_id, branch_id=g.branch_id).customer_detail(
            customer_id
        )
        return model_response(customer_detail_response(detail))
