"""Thin product catalogue API routes with conditional GET support."""

from __future__ import annotations

import hashlib
from pathlib import Path

from flask import Blueprint, Response, current_app, g, request, send_file
from sqlalchemy.orm import Session

from vglpos.api.v1.http import model_response, parse_body, parse_query
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.common import StatusResponse
from vglpos.api.v1.schemas.products import (
    BarcodeLabelsRequest,
    BulkPriceUpdateRequest,
    BulkPriceUpdateResponse,
    CatalogDeltaQuery,
    CatalogDeltaResponse,
    CategoryListResponse,
    CategoryResponse,
    ProductCreateRequest,
    ProductImportCommitResponse,
    ProductImportPreviewResponse,
    ProductImportRowResponse,
    ProductLookupQuery,
    ProductPageResponse,
    ProductQuery,
    ProductResponse,
    ProductUpdateRequest,
)
from vglpos.api.v1.serializers import catalog_product_response, product_response
from vglpos.extensions import db
from vglpos.security.decorators import require_permission
from vglpos.services.barcode_label_service import BarcodeLabelService
from vglpos.services.cache_service import catalogue_key, get_mapping, set_mapping
from vglpos.services.catalog_operations_service import (
    BulkPriceUpdateCommand,
    CatalogOperationsService,
)
from vglpos.services.catalog_service import (
    CatalogService,
    CreateProductCommand,
    UpdateProductCommand,
)
from vglpos.services.exceptions import ValidationError

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


def _import_file() -> tuple[str, bytes]:
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        raise ValidationError("A CSV or XLSX file is required.")
    return uploaded.filename, uploaded.read()


def _import_preview_response(preview: object) -> ProductImportPreviewResponse:
    return ProductImportPreviewResponse(
        total_rows=preview.total_rows,
        valid_rows=preview.valid_rows,
        invalid_rows=preview.invalid_rows,
        rows=[ProductImportRowResponse.model_validate(row) for row in preview.rows],
    )


@products_bp.post("/import/preview")
@require_permission("product.create")
@idempotent
@documented(
    summary="Dry-run a CSV or XLSX product import",
    response_model=ProductImportPreviewResponse,
)
def preview_import() -> tuple[Response, int]:
    filename, content = _import_file()
    with Session(db.engine) as session:
        preview = CatalogOperationsService(session, g.company_id).preview_import(filename, content)
        return model_response(_import_preview_response(preview))


@products_bp.post("/import/commit")
@require_permission("product.create")
@idempotent
@documented(
    summary="Commit a fully valid CSV or XLSX product import",
    response_model=ProductImportCommitResponse,
    success_status=201,
)
def commit_import() -> tuple[Response, int]:
    filename, content = _import_file()
    with Session(db.engine) as session:
        products = CatalogOperationsService(session, g.company_id).commit_import(
            filename, content, user_id=g.user_id
        )
        return model_response(ProductImportCommitResponse(imported_count=len(products)), status=201)


@products_bp.post("/import/error-report")
@require_permission("product.create")
@idempotent
@documented(summary="Download product-import validation errors")
def import_error_report() -> Response:
    filename, content = _import_file()
    with Session(db.engine) as session:
        report = CatalogOperationsService(session, g.company_id).error_report(filename, content)
    return Response(
        report,
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=product-import-errors.csv"},
    )


@products_bp.post("/bulk-price-update")
@require_permission("product.edit")
@idempotent
@documented(
    summary="Apply a manager-approved bulk price percentage",
    request_model=BulkPriceUpdateRequest,
    response_model=BulkPriceUpdateResponse,
)
def bulk_price_update() -> tuple[Response, int]:
    body = parse_body(BulkPriceUpdateRequest)
    with Session(db.engine) as session:
        result = CatalogOperationsService(session, g.company_id).bulk_price_update(
            BulkPriceUpdateCommand(
                company_id=g.company_id,
                actor_user_id=g.user_id,
                category_id=body.category_id,
                percentage=body.percentage,
                approver_user_id=body.approver_user_id,
                approval_pin=body.approval_pin,
                reason=body.reason,
            )
        )
        return model_response(BulkPriceUpdateResponse.model_validate(result))


@products_bp.post("/barcode-labels")
@require_permission("product.view")
@idempotent
@documented(
    summary="Generate printable Code128 or EAN13 barcode labels",
    request_model=BarcodeLabelsRequest,
)
def barcode_labels() -> Response:
    body = parse_body(BarcodeLabelsRequest)
    with Session(db.engine) as session:
        svg = BarcodeLabelService(session, g.company_id).render(
            body.product_ids,
            symbology=body.symbology,
            width_mm=body.width_mm,
            height_mm=body.height_mm,
        )
    return Response(
        svg,
        content_type="image/svg+xml; charset=utf-8",
        headers={"Content-Disposition": "inline; filename=barcode-labels.svg"},
    )


def _image_root() -> Path:
    configured = str(current_app.config["PRODUCT_IMAGE_DIR"]).strip()
    return Path(configured) if configured else Path(current_app.instance_path) / "product-images"


@products_bp.post("/<int:product_id>/image")
@require_permission("product.edit")
@idempotent
@documented(summary="Upload and safely resize a product image", response_model=ProductResponse)
def upload_product_image(product_id: int) -> tuple[Response, int]:
    uploaded = request.files.get("image")
    if uploaded is None:
        raise ValidationError("A product image is required.")
    with Session(db.engine) as session:
        product = CatalogOperationsService(session, g.company_id).store_product_image(
            product_id,
            user_id=g.user_id,
            content=uploaded.read(),
            storage_root=_image_root(),
        )
        return model_response(product_response(product))


@products_bp.get("/<int:product_id>/image")
@require_permission("product.view")
@documented(summary="Read a safely re-encoded product image")
def get_product_image(product_id: int) -> Response:
    with Session(db.engine) as session:
        path = CatalogOperationsService(session, g.company_id).product_image_path(
            product_id, storage_root=_image_root()
        )
    return send_file(path, mimetype="image/webp", conditional=True, max_age=86400)
