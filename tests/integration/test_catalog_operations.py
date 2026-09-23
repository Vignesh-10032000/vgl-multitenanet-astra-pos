"""Phase 7 catalogue import, bulk pricing, labels, and image tests."""

from __future__ import annotations

import io
import zipfile
from decimal import Decimal
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vglpos.domain.models import (
    Permission,
    Product,
    ProductPriceHistory,
    Role,
    RolePermission,
    UserRole,
)
from vglpos.security.password import hash_pin
from vglpos.services.barcode_label_service import BarcodeLabelService
from vglpos.services.catalog_operations_service import (
    BulkPriceUpdateCommand,
    CatalogOperationsService,
)

from .conftest import ServiceContext


def _csv(context: ServiceContext, *rows: str) -> bytes:
    header = "sku,name,tax_rate_id,cost_price,selling_price,mrp,barcode,is_active"
    return ("\n".join((header, *rows)) + "\n").encode()


def _xlsx(context: ServiceContext) -> bytes:
    rows = (
        ("sku", "name", "tax_rate_id", "cost_price", "selling_price", "mrp"),
        ("XLSX-001", "Spreadsheet product", str(context.tax_rate.id), "10", "20", "25"),
    )
    sheet_rows = []
    for row_number, row in enumerate(rows, start=1):
        cells = "".join(
            f'<c r="{chr(65 + index)}{row_number}" t="inlineStr"><is><t>{value}</t></is></c>'
            for index, value in enumerate(row)
        )
        sheet_rows.append(f'<row r="{row_number}">{cells}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return content.getvalue()


def _grant_product_manager(session: Session, context: ServiceContext) -> None:
    permission = Permission(
        code="product.edit",
        description="Edit products",
        category="product",
    )
    role = Role(
        company_id=context.company.id,
        name="MANAGER",
        description="Catalogue manager",
        is_system=True,
    )
    context.cashier.pin_hash = hash_pin("2468")
    session.add_all([permission, role])
    session.flush()
    session.add_all(
        [
            RolePermission(
                company_id=context.company.id,
                role_id=role.id,
                permission_id=permission.id,
            ),
            UserRole(
                company_id=context.company.id,
                user_id=context.cashier.id,
                role_id=role.id,
            ),
        ]
    )
    session.commit()


def test_csv_import_dry_run_commit_and_error_report(
    service_session: Session, service_context: ServiceContext
) -> None:
    service = CatalogOperationsService(service_session, service_context.company.id)
    valid = _csv(
        service_context,
        (
            f"NEW-001,Imported product,{service_context.tax_rate.id},"
            "10.00,20.00,25.00,890123456789,true"
        ),
    )

    preview = service.preview_import("products.csv", valid)
    imported = service.commit_import("products.csv", valid, user_id=service_context.cashier.id)

    assert preview.total_rows == preview.valid_rows == 1
    assert preview.invalid_rows == 0
    assert imported[0].sku == "NEW-001"
    invalid = _csv(
        service_context,
        ",,999,not-money,-1.00,0.00,,perhaps",
        f"{service_context.product.sku},Duplicate,{service_context.tax_rate.id},1,2,3,{service_context.product.barcode},true",
    )
    errors = service.preview_import("products.csv", invalid)
    report = service.error_report("products.csv", invalid).decode("utf-8-sig")
    assert errors.invalid_rows == 2
    assert "sku is required" in errors.rows[0].errors
    assert "name is required" in errors.rows[0].errors
    assert "tax_rate_id was not found" in errors.rows[0].errors
    assert "cost_price must be a valid amount" in errors.rows[0].errors
    assert any("is_active must be true/false" in error for error in errors.rows[0].errors)
    assert "sku already exists" in errors.rows[1].errors[0]
    assert "barcode already exists" in " | ".join(errors.rows[1].errors)
    assert "row_number,sku,errors" in report


def test_xlsx_import_preview_reads_first_worksheet(
    service_session: Session, service_context: ServiceContext
) -> None:
    preview = CatalogOperationsService(service_session, service_context.company.id).preview_import(
        "products.xlsx", _xlsx(service_context)
    )

    assert preview.total_rows == 1
    assert preview.valid_rows == 1
    assert preview.rows[0].sku == "XLSX-001"


def test_bulk_price_update_is_approved_and_history_is_complete(
    service_session: Session, service_context: ServiceContext
) -> None:
    _grant_product_manager(service_session, service_context)
    result = CatalogOperationsService(
        service_session, service_context.company.id
    ).bulk_price_update(
        BulkPriceUpdateCommand(
            company_id=service_context.company.id,
            actor_user_id=service_context.cashier.id,
            percentage="10.00",
            approver_user_id=service_context.cashier.id,
            approval_pin="2468",
            reason="Approved seasonal increase",
        )
    )

    service_session.refresh(service_context.product)
    history = service_session.scalar(
        select(ProductPriceHistory).where(
            ProductPriceHistory.product_id == service_context.product.id
        )
    )
    assert result.updated_count == 1
    assert service_context.product.selling_price == Decimal("110.00")
    assert service_context.product.mrp == Decimal("129.80")
    assert history is not None
    assert history.old_selling_price == Decimal("100.00")
    assert history.new_selling_price == Decimal("110.00")


def test_barcode_labels_and_image_upload_are_safe(
    service_session: Session, service_context: ServiceContext, tmp_path: Path
) -> None:
    labels = BarcodeLabelService(service_session, service_context.company.id).render(
        [service_context.product.id],
        symbology="AUTO",
        width_mm=Decimal("50.00"),
        height_mm=Decimal("30.00"),
    )
    assert labels.startswith("<?xml")
    assert "<rect" in labels
    assert service_context.product.barcode in labels

    source = io.BytesIO()
    Image.new("RGB", (1600, 1200), color=(10, 120, 80)).save(source, format="PNG")
    service = CatalogOperationsService(service_session, service_context.company.id)
    product = service.store_product_image(
        service_context.product.id,
        user_id=service_context.cashier.id,
        content=source.getvalue(),
        storage_root=tmp_path,
    )
    assert product.image_path is not None
    stored = service.product_image_path(product.id, storage_root=tmp_path)
    with Image.open(stored) as image:
        assert image.format == "WEBP"
        assert image.width <= 800
        assert image.height <= 800
    assert service_session.scalar(select(func.count()).select_from(Product)) == 1
