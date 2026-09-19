"""Pure response-model construction kept out of route handlers."""

from __future__ import annotations

from vglpos.api.v1.schemas.customers import CustomerDetailResponse, CustomerResponse
from vglpos.api.v1.schemas.products import ProductResponse
from vglpos.api.v1.schemas.reports import (
    DailySummaryResponse,
    Gstr1Response,
    Gstr1RowResponse,
    InventoryValuationResponse,
    InventoryValuationRowResponse,
)
from vglpos.api.v1.schemas.sales import (
    QuoteLineResponse,
    QuoteResponse,
    SaleDetailResponse,
    SaleLineResponse,
    SalePaymentResponse,
    SaleResponse,
)
from vglpos.api.v1.schemas.shifts import CashMovementResponse, ShiftResponse
from vglpos.services.customer_service import CustomerDetail
from vglpos.services.report_service import DailySummary, Gstr1Row, InventoryValuation
from vglpos.services.sales_service import SaleDetail
from vglpos.services.tax_engine import TaxResult


def product_response(product: object) -> ProductResponse:
    return ProductResponse.model_validate(product)


def customer_response(customer: object) -> CustomerResponse:
    return CustomerResponse.model_validate(customer)


def sale_response(sale: object) -> SaleResponse:
    return SaleResponse.model_validate(sale)


def sale_detail_response(detail: SaleDetail) -> SaleDetailResponse:
    base = sale_response(detail.sale).model_dump()
    return SaleDetailResponse(
        **base,
        items=[SaleLineResponse.model_validate(item) for item in detail.items],
        payments=[SalePaymentResponse.model_validate(payment) for payment in detail.payments],
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


def shift_response(shift: object) -> ShiftResponse:
    return ShiftResponse.model_validate(shift)


def cash_movement_response(movement: object) -> CashMovementResponse:
    return CashMovementResponse.model_validate(movement)


def daily_summary_response(summary: DailySummary) -> DailySummaryResponse:
    return DailySummaryResponse.model_validate(summary)


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
