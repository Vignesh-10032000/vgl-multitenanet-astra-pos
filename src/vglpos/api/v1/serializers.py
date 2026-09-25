"""Pure response-model construction kept out of route handlers."""

from __future__ import annotations

from vglpos.api.v1.schemas.customers import CustomerDetailResponse, CustomerResponse
from vglpos.api.v1.schemas.products import CatalogProductResponse, ProductResponse
from vglpos.api.v1.schemas.reports import (
    DailySummaryResponse,
    Gstr1Response,
    Gstr1RowResponse,
    InventoryValuationResponse,
    InventoryValuationRowResponse,
    RevenuePointResponse,
    RevenueSeriesResponse,
)
from vglpos.api.v1.schemas.sales import (
    EInvoiceReceiptResponse,
    PaymentPreviewResponse,
    QuoteLineResponse,
    QuoteResponse,
    SaleDetailResponse,
    SaleLineResponse,
    SalePaymentResponse,
    SaleResponse,
)
from vglpos.api.v1.schemas.shifts import CashMovementResponse, ShiftResponse
from vglpos.services.catalog_service import CatalogRecord
from vglpos.services.checkout_service import PaymentPreview
from vglpos.services.customer_service import CustomerDetail
from vglpos.services.qr_service import qr_png_data_uri
from vglpos.services.report_service import (
    DailySummary,
    Gstr1Row,
    InventoryValuation,
    RevenuePoint,
)
from vglpos.services.sales_service import SaleDetail
from vglpos.services.tax_engine import TaxResult
from vglpos.utils.money import ZERO, money


def product_response(product: object) -> ProductResponse:
    return ProductResponse.model_validate(product)


def catalog_product_response(record: CatalogRecord) -> CatalogProductResponse:
    """Attach effective GST facts and tombstone state to an offline catalogue row."""
    return CatalogProductResponse(
        **product_response(record.product).model_dump(),
        tax_rate=record.tax_rate,
        cess_rate=record.cess_rate,
        deleted_at=record.product.deleted_at,
    )


def customer_response(customer: object) -> CustomerResponse:
    return CustomerResponse.model_validate(customer)


def sale_response(sale: object) -> SaleResponse:
    return SaleResponse.model_validate(sale)


def sale_detail_response(detail: SaleDetail) -> SaleDetailResponse:
    base = sale_response(detail.sale).model_dump()
    return SaleDetailResponse(
        **base,
        items=[
            SaleLineResponse(
                id=item.id,
                product_id=item.product_id,
                sku=detail.products[item.product_id].sku,
                name=detail.products[item.product_id].name,
                name_en=detail.products[item.product_id].name_en,
                name_ta=detail.products[item.product_id].name_ta,
                line_number=item.line_number,
                quantity=item.quantity,
                unit_price=item.unit_price,
                gross_amount=item.gross_amount,
                discount_amount=item.discount_amount,
                taxable_amount=item.taxable_amount,
                tax_rate=item.tax_rate,
                cgst_amount=item.cgst_amount,
                sgst_amount=item.sgst_amount,
                igst_amount=item.igst_amount,
                cess_amount=item.cess_amount,
                total_amount=item.total_amount,
            )
            for item in detail.items
        ],
        payments=[SalePaymentResponse.model_validate(payment) for payment in detail.payments],
        e_invoice=(
            EInvoiceReceiptResponse(
                status=detail.e_invoice.status,
                irn=detail.e_invoice.irn,
                ack_number=detail.e_invoice.ack_number,
                ack_date=detail.e_invoice.ack_date,
                qr_data_uri=(
                    qr_png_data_uri(detail.e_invoice.signed_qr_code)
                    if detail.e_invoice.signed_qr_code
                    else None
                ),
            )
            if detail.e_invoice is not None
            else None
        ),
        composition_declaration=detail.composition_declaration,
    )


def customer_detail_response(detail: CustomerDetail) -> CustomerDetailResponse:
    base = customer_response(detail.customer).model_dump()
    return CustomerDetailResponse(
        **base,
        purchases=[sale_response(sale) for sale in detail.purchases],
    )


def quote_response(result: TaxResult) -> QuoteResponse:
    return QuoteResponse(
        lines=[
            QuoteLineResponse(
                quantity=line.quantity,
                unit_price=line.unit_price,
                gross_amount=line.gross_amount,
                discount_amount=line.discount_amount,
                taxable_amount=line.taxable_amount,
                tax_rate=line.tax_rate,
                cess_rate=line.cess_rate,
                cgst_amount=line.cgst_amount,
                sgst_amount=line.sgst_amount,
                igst_amount=line.igst_amount,
                cess_amount=line.cess_amount,
                total_amount=line.line_total,
            )
            for line in result.lines
        ],
        is_interstate=result.is_interstate,
        gross_amount=result.gross_amount,
        discount_amount=result.discount_amount,
        taxable_amount=result.taxable_amount,
        cgst_amount=result.cgst_amount,
        sgst_amount=result.sgst_amount,
        igst_amount=result.igst_amount,
        cess_amount=result.cess_amount,
        round_off=result.round_off,
        net_amount=result.net_amount,
    )


def payment_preview_response(preview: PaymentPreview) -> PaymentPreviewResponse:
    """Combine exact quote and tender facts without client-side arithmetic."""
    return PaymentPreviewResponse(
        **quote_response(preview.quote).model_dump(),
        amount_received=preview.amount_received,
        change_due=preview.change_due,
        balance_due=preview.balance_due,
    )


def shift_response(shift: object) -> ShiftResponse:
    return ShiftResponse.model_validate(shift)


def cash_movement_response(movement: object) -> CashMovementResponse:
    return CashMovementResponse.model_validate(movement)


def daily_summary_response(summary: DailySummary) -> DailySummaryResponse:
    return DailySummaryResponse.model_validate(summary)


def revenue_series_response(rows: tuple[RevenuePoint, ...]) -> RevenueSeriesResponse:
    return RevenueSeriesResponse(
        items=[RevenuePointResponse.model_validate(row) for row in rows],
        total_bills=sum(row.total_bills for row in rows),
        net_amount=money(sum((row.net_amount for row in rows), ZERO)),
    )


def gstr1_response(rows: tuple[Gstr1Row, ...]) -> Gstr1Response:
    return Gstr1Response(items=[Gstr1RowResponse.model_validate(row) for row in rows])


def inventory_valuation_response(
    valuation: InventoryValuation,
) -> InventoryValuationResponse:
    return InventoryValuationResponse(
        method=valuation.method,
        items=[InventoryValuationRowResponse.model_validate(row) for row in valuation.items],
        total_value=valuation.total_value,
    )
