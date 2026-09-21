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
    CatalogDeltaQuery,
    CatalogDeltaResponse,
    CategoryListResponse,
    CategoryResponse,
    ProductCreateRequest,
    ProductLookupQuery,
    ProductPageResponse,
    ProductQuery,
    ProductResponse,
    ProductUpdateRequest,
)
from vglpos.api.v1.serializers import catalog_product_response, product_response
from vglpos.extensions import db
from vglpos.security.decorators import require_permission
from vglpos.services.cache_service import catalogue_key, get_mapping, set_mapping
from vglpos.services.catalog_service import (
    CatalogService,
    CreateProductCommand,
    UpdateProductCommand,
)

products_bp = Blueprint("products", __name__, url_prefix="/api/v1/products")


@products_bp.get("/categories")
@require_permission("product.view")
@documented(
    summary="List active product categories",
    response_model=CategoryListResponse,
)
def list_categories() -> tuple[Response, int]:
    """Expose localized category labels through the catalogue service."""
    with Session(db.engine) as session:
        categories = CatalogService(session, g.company_id).list_categories()
        return model_response(
            CategoryListResponse(
                items=[CategoryResponse.model_validate(category) for category in categories]
            )
        )


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
    key = catalogue_key(
        company_id=g.company_id,
        branch_id=g.branch_id,
        cursor=query.cursor,
        limit=query.limit,
        query=query.q,
        barcode=query.barcode,
    )
    cached = get_mapping(key)
    if cached is not None:
        return _etag_response(ProductPageResponse.model_validate(cached))
    with Session(db.engine) as session:
        page = CatalogService(session, g.company_id).list_products(
            cursor=query.cursor, limit=query.limit, query=query.q, barcode=query.barcode
        )
        result = ProductPageResponse(
            items=[product_response(item) for item in page.items], next_cursor=page.next_cursor
        )
        set_mapping(key, result.model_dump(mode="json"))
        return _etag_response(result)


@products_bp.get("/catalog")
@require_permission("product.view")
@documented(
    summary="Delta-sync the offline product catalogue",
    query_model=CatalogDeltaQuery,
    response_model=CatalogDeltaResponse,
)
def catalog_delta() -> tuple[Response, int]:
    query = parse_query(CatalogDeltaQuery)
    with Session(db.engine) as session:
        delta = CatalogService(session, g.company_id).catalog_delta(
            since=query.since,
            limit=query.limit,
        )
        return model_response(
            CatalogDeltaResponse(
                items=[catalog_product_response(item) for item in delta.items],
                synced_at=delta.synced_at,
                truncated=delta.truncated,
            )
        )


@products_bp.get("/lookup")
@require_permission("product.view")
@documented(
    summary="Look up a product by barcode",
    query_model=ProductLookupQuery,
    response_model=ProductResponse,
)
def lookup_product() -> tuple[Response, int]:
    query = parse_query(ProductLookupQuery)
    with Session(db.engine) as session:
        product = CatalogService(session, g.company_id).lookup_by_barcode(query.barcode)
        return model_response(product_response(product))


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
