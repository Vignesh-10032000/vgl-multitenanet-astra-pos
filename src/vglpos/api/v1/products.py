"""Thin product catalogue API routes with conditional GET support."""

from __future__ import annotations

import hashlib

from flask import Blueprint, Response, g, request
from sqlalchemy.orm import Session

from vglpos.api.v1.http import model_response, parse_body, parse_query
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.common import StatusResponse
from vglpos.api.v1.schemas.products import (
    ProductCreateRequest,
    ProductPageResponse,
    ProductQuery,
    ProductResponse,
    ProductUpdateRequest,
)
from vglpos.api.v1.serializers import product_response
from vglpos.extensions import db
from vglpos.security.decorators import require_permission
from vglpos.services.catalog_service import (
    CatalogService,
    CreateProductCommand,
    UpdateProductCommand,
)

products_bp = Blueprint("products", __name__, url_prefix="/api/v1/products")


def _etag_response(page: ProductPageResponse) -> tuple[Response, int]:
    response, status = model_response(page)
    etag = hashlib.sha256(response.get_data()).hexdigest()
    if request.if_none_match.contains(etag):
        not_modified = Response(status=304)
        not_modified.set_etag(etag)
        return not_modified, 304
    response.set_etag(etag)
    return response, status


@products_bp.get("")
@require_permission("product.view")
@documented(
    summary="List and search the product catalogue",
    query_model=ProductQuery,
    response_model=ProductPageResponse,
)
def list_products() -> tuple[Response, int]:
    query = parse_query(ProductQuery)
    with Session(db.engine) as session:
        page = CatalogService(session, g.company_id).list_products(
            cursor=query.cursor, limit=query.limit, query=query.q, barcode=query.barcode
        )
        result = ProductPageResponse(
            items=[product_response(item) for item in page.items], next_cursor=page.next_cursor
        )
        return _etag_response(result)


@products_bp.post("")
@require_permission("product.create")
@idempotent
@documented(
    summary="Create a product",
    request_model=ProductCreateRequest,
    response_model=ProductResponse,
    success_status=201,
)
def create_product() -> tuple[Response, int]:
    body = parse_body(ProductCreateRequest)
    command = CreateProductCommand(g.company_id, g.user_id, body.model_dump())
    with Session(db.engine) as session:
        product = CatalogService(session, g.company_id).create_product(command)
        return model_response(product_response(product), status=201)


@products_bp.put("/<int:product_id>")
@require_permission("product.edit")
@idempotent
@documented(
    summary="Update a product",
    request_model=ProductUpdateRequest,
    response_model=ProductResponse,
)
def update_product(product_id: int) -> tuple[Response, int]:
    body = parse_body(ProductUpdateRequest)
    values = body.model_dump(exclude_unset=True)
    command = UpdateProductCommand(g.company_id, g.user_id, product_id, values)
    with Session(db.engine) as session:
        product = CatalogService(session, g.company_id).update_product(command)
        return model_response(product_response(product))


@products_bp.delete("/<int:product_id>")
@require_permission("product.delete")
@documented(summary="Soft-delete a product", response_model=StatusResponse)
def delete_product(product_id: int) -> tuple[Response, int]:
    with Session(db.engine) as session:
        CatalogService(session, g.company_id).delete_product(product_id, user_id=g.user_id)
        return model_response(StatusResponse(status="deleted"))
