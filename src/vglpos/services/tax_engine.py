"""Pure, deterministic GST calculation for sale and invoice services.

This module has no application, database, clock, or I/O dependency. Callers provide the
effective tax rate and jurisdiction facts; the engine returns an immutable calculation
that can be stored or rendered without repeating financial arithmetic elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Final

from vglpos.utils.gst import is_interstate
from vglpos.utils.money import MONEY_QUANTUM, ZERO, apportion, money, qty, round_off_to_rupee
from vglpos.utils.money import to_decimal as _to_decimal

_HUNDRED: Final = Decimal("100")
_ONE: Final = Decimal("1")


@dataclass(frozen=True, slots=True)
class TaxLineInput:
    """Capture caller-supplied line facts before strict Decimal validation."""

    quantity: object
    unit_price: object
    tax_rate: object
    line_discount: object = ZERO
    cess_rate: object = ZERO
    tax_inclusive: bool = False


@dataclass(frozen=True, slots=True)
class TaxLineResult:
    """Expose every rounded line component needed for invoice persistence and audit."""

    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    cess_rate: Decimal
    tax_inclusive: bool
    gross_amount: Decimal
    line_discount_amount: Decimal
    order_discount_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    line_total: Decimal


@dataclass(frozen=True, slots=True)
class TaxResult:
    """Represent a fully rolled-up invoice calculation with an explicit round-off."""

    lines: tuple[TaxLineResult, ...]
    is_interstate: bool
    gross_amount: Decimal
    line_discount_amount: Decimal
    order_discount_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    round_off: Decimal
    net_amount: Decimal

    def assert_reconciles(self) -> None:
        """Reject a result whose stored statutory components cannot reproduce its total."""
        components = money(
            self.taxable_amount
            + self.cgst_amount
            + self.sgst_amount
            + self.igst_amount
            + self.cess_amount
            + self.round_off
        )
        difference = abs(components - self.net_amount)
        if difference > MONEY_QUANTUM:
            raise ValueError(
                "Invoice does not reconcile: taxable value, tax, cess, and round-off "
                "do not equal net amount."
            )


@dataclass(frozen=True, slots=True)
class _PreparedLine:
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    cess_rate: Decimal
    tax_inclusive: bool
    gross_amount: Decimal
    line_discount_amount: Decimal
    discountable_amount: Decimal


def _numeric(value: object, *, line_number: int, field: str) -> Decimal:
    try:
        return _to_decimal(value)
    except ValueError as exc:
        raise ValueError(f"Line {line_number} {field} must be numeric.") from exc


def _prepare_line(line: TaxLineInput, line_number: int) -> _PreparedLine:
    raw_quantity = _numeric(line.quantity, line_number=line_number, field="quantity")
    if raw_quantity <= 0:
        raise ValueError(f"Line {line_number} quantity must be greater than zero.")
    quantity = qty(raw_quantity)
    if quantity == 0:
        raise ValueError(f"Line {line_number} quantity must be at least 0.001.")

    raw_price = _numeric(line.unit_price, line_number=line_number, field="unit price")
    if raw_price < 0:
        raise ValueError(f"Line {line_number} unit price cannot be negative.")
    unit_price = money(raw_price)

    raw_tax_rate = _numeric(line.tax_rate, line_number=line_number, field="tax rate")
    if raw_tax_rate < 0 or raw_tax_rate > 100:
        raise ValueError(f"Line {line_number} tax rate must be between 0 and 100.")
    tax_rate = money(raw_tax_rate)

    raw_cess_rate = _numeric(line.cess_rate, line_number=line_number, field="cess rate")
    if raw_cess_rate < 0 or raw_cess_rate > 100:
        raise ValueError(f"Line {line_number} cess rate must be between 0 and 100.")
    cess_rate = money(raw_cess_rate)

    raw_line_discount = _numeric(line.line_discount, line_number=line_number, field="line discount")
    if raw_line_discount < 0:
        raise ValueError(f"Line {line_number} line discount cannot be negative.")
    line_discount = money(raw_line_discount)
    gross = money(quantity * unit_price)
    if line_discount > gross:
        raise ValueError(f"Line {line_number} line discount cannot exceed line gross.")
    if not isinstance(line.tax_inclusive, bool):
        raise ValueError(f"Line {line_number} tax-inclusive flag must be boolean.")

    return _PreparedLine(
        quantity=quantity,
        unit_price=unit_price,
        tax_rate=tax_rate,
        cess_rate=cess_rate,
        tax_inclusive=line.tax_inclusive,
        gross_amount=gross,
        line_discount_amount=line_discount,
        discountable_amount=money(gross - line_discount),
    )


def _tax_components(
    line: _PreparedLine, order_discount: Decimal, interstate: bool
) -> TaxLineResult:
    discounted_value = money(line.discountable_amount - order_discount)
    combined_rate = line.tax_rate + line.cess_rate

    if line.tax_inclusive:
        taxable = money(discounted_value / (_ONE + combined_rate / _HUNDRED))
        included_tax = money(discounted_value - taxable)
        gst_total, cess = apportion(included_tax, [line.tax_rate, line.cess_rate])
    else:
        taxable = discounted_value
        gst_total = money(taxable * line.tax_rate / _HUNDRED)
        cess = money(taxable * line.cess_rate / _HUNDRED)

    if interstate:
        cgst = ZERO
        sgst = ZERO
        igst = gst_total
    else:
        cgst = (gst_total / 2).quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)
        sgst = money(gst_total - cgst)
        igst = ZERO

    total_discount = money(line.line_discount_amount + order_discount)
    line_total = money(taxable + cgst + sgst + igst + cess)
    return TaxLineResult(
        quantity=line.quantity,
        unit_price=line.unit_price,
        tax_rate=line.tax_rate,
        cess_rate=line.cess_rate,
        tax_inclusive=line.tax_inclusive,
        gross_amount=line.gross_amount,
        line_discount_amount=line.line_discount_amount,
        order_discount_amount=order_discount,
        discount_amount=total_discount,
        taxable_amount=taxable,
        cgst_amount=cgst,
        sgst_amount=sgst,
        igst_amount=igst,
        cess_amount=cess,
        line_total=line_total,
    )


class TaxEngine:
    """Calculate GST invoices without retaining state between calls."""

    @staticmethod
    def compute(
        lines: list[TaxLineInput],
        *,
        supplier_state: str,
        place_of_supply: str,
        order_discount: Decimal = ZERO,
        apply_round_off: bool = True,
    ) -> TaxResult:
        """Compute discounts before tax and return an exactly reconciling invoice.

        Order discounts are weighted by each line's value remaining after its line-level
        discount. This prevents a fully discounted line from receiving another discount
        and becoming negative.
        """
        if not lines:
            raise ValueError("At least one tax line is required.")
        if not isinstance(apply_round_off, bool):
            raise ValueError("Apply-round-off flag must be boolean.")

        prepared = [_prepare_line(line, index) for index, line in enumerate(lines, start=1)]
        try:
            raw_order_discount = _to_decimal(order_discount)
        except ValueError as exc:
            raise ValueError("Order discount must be numeric.") from exc
        if raw_order_discount < 0:
            raise ValueError("Order discount cannot be negative.")
        rounded_order_discount = money(raw_order_discount)

        discountable_total = money(
            sum((line.discountable_amount for line in prepared), Decimal("0"))
        )
        if rounded_order_discount > discountable_total:
            raise ValueError("Order discount cannot exceed the order value.")

        interstate = is_interstate(supplier_state, place_of_supply)
        allocated_discounts = apportion(
            rounded_order_discount, [line.discountable_amount for line in prepared]
        )
        calculated_lines = tuple(
            _tax_components(line, allocated_discount, interstate)
            for line, allocated_discount in zip(prepared, allocated_discounts, strict=True)
        )

        gross = money(sum((line.gross_amount for line in calculated_lines), Decimal("0")))
        line_discounts = money(
            sum((line.line_discount_amount for line in calculated_lines), Decimal("0"))
        )
        taxable = money(sum((line.taxable_amount for line in calculated_lines), Decimal("0")))
        cgst = money(sum((line.cgst_amount for line in calculated_lines), Decimal("0")))
        sgst = money(sum((line.sgst_amount for line in calculated_lines), Decimal("0")))
        igst = money(sum((line.igst_amount for line in calculated_lines), Decimal("0")))
        cess = money(sum((line.cess_amount for line in calculated_lines), Decimal("0")))
        before_round_off = money(taxable + cgst + sgst + igst + cess)
        if apply_round_off:
            net_amount, round_off = round_off_to_rupee(before_round_off)
        else:
            net_amount = before_round_off
            round_off = ZERO

        result = TaxResult(
            lines=calculated_lines,
            is_interstate=interstate,
            gross_amount=gross,
            line_discount_amount=line_discounts,
            order_discount_amount=rounded_order_discount,
            discount_amount=money(line_discounts + rounded_order_discount),
            taxable_amount=taxable,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            cess_amount=cess,
            round_off=round_off,
            net_amount=net_amount,
        )
        result.assert_reconciles()
        return result
