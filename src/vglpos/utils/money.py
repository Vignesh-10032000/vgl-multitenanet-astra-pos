"""Exact Decimal helpers for Indian retail money and quantities.

Binary floating-point arithmetic is deliberately contained at the input boundary. Every
public helper returns a finite :class:`~decimal.Decimal` so business calculations never
inherit binary representation errors.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

MONEY_QUANTUM: Final = Decimal("0.01")
QTY_QUANTUM: Final = Decimal("0.001")
RUPEE_QUANTUM: Final = Decimal("1")
ZERO: Final = Decimal("0.00")

_ONES: Final[tuple[str, ...]] = (
    "Zero",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)
_TENS: Final[tuple[str, ...]] = (
    "",
    "",
    "Twenty",
    "Thirty",
    "Forty",
    "Fifty",
    "Sixty",
    "Seventy",
    "Eighty",
    "Ninety",
)


def to_decimal(value: object) -> Decimal:
    """Coerce user input without exposing calculations to binary-float artefacts.

    Floats are converted through their human-readable string form, never passed directly
    to ``Decimal``. Booleans and non-finite values are rejected because accepting them as
    monetary values usually hides an upstream validation defect.

    Examples:
        >>> to_decimal(0.1)
        Decimal('0.1')
        >>> to_decimal(" 12.50 ")
        Decimal('12.50')
        >>> to_decimal(True)
        Traceback (most recent call last):
        ...
        ValueError: Value must be a finite decimal number.
    """
    if isinstance(value, bool):
        raise ValueError("Value must be a finite decimal number.")

    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str, float)):
        source = str(value).strip()
        if not source:
            raise ValueError("Value must be a finite decimal number.")
        try:
            result = Decimal(source)
        except InvalidOperation as exc:
            raise ValueError("Value must be a finite decimal number.") from exc
    else:
        raise ValueError("Value must be a finite decimal number.")

    if not result.is_finite():
        raise ValueError("Value must be a finite decimal number.")
    return result


def money(value: object) -> Decimal:
    """Round a finite value to paise using Indian retail half-up rounding.

    Examples:
        >>> money("10.005")
        Decimal('10.01')
        >>> money("10.004")
        Decimal('10.00')
    """
    try:
        return to_decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Money value is outside the supported decimal range.") from exc


def qty(value: object) -> Decimal:
    """Round a quantity to the schema's three-decimal unit precision.

    Examples:
        >>> qty("1.2345")
        Decimal('1.235')
        >>> qty("2")
        Decimal('2.000')
    """
    try:
        return to_decimal(value).quantize(QTY_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Quantity is outside the supported decimal range.") from exc


def round_off_to_rupee(value: object) -> tuple[Decimal, Decimal]:
    """Return the nearest whole-rupee invoice total and its auditable delta.

    The delta is positive when rounding increases the amount payable and negative when it
    decreases it, allowing the stored invoice components to reconcile exactly.

    Examples:
        >>> round_off_to_rupee("100.49")
        (Decimal('100.00'), Decimal('-0.49'))
        >>> round_off_to_rupee("100.50")
        (Decimal('101.00'), Decimal('0.50'))
    """
    amount = money(value)
    rounded = amount.quantize(RUPEE_QUANTUM, rounding=ROUND_HALF_UP).quantize(MONEY_QUANTUM)
    return rounded, money(rounded - amount)


def apportion(total: object, weights: Sequence[object]) -> list[Decimal]:
    """Split paise exactly by largest remainder with stable tie-breaking.

    Allocations are first floored to whole paise. Remaining paise are assigned to the
    largest fractional remainders, with input order breaking ties. This preserves both the
    requested total and deterministic invoice output.

    Examples:
        >>> apportion("0.05", [1, 1, 1])
        [Decimal('0.02'), Decimal('0.02'), Decimal('0.01')]
        >>> sum(apportion("50.00", [100, 200, 300]))
        Decimal('50.00')
    """
    amount = money(total)
    if not weights:
        if amount == ZERO:
            return []
        raise ValueError("At least one weight is required for a non-zero total.")

    decimal_weights = [to_decimal(weight) for weight in weights]
    if any(weight < 0 for weight in decimal_weights):
        raise ValueError("Apportionment weights cannot be negative.")

    weight_sum = sum(decimal_weights, Decimal("0"))
    if amount == ZERO:
        return [ZERO for _ in decimal_weights]
    if weight_sum == 0:
        raise ValueError("Apportionment weights must contain a positive value.")

    sign = Decimal("-1") if amount < 0 else Decimal("1")
    paisa_total = int((abs(amount) * 100).to_integral_exact())
    exact_shares = [Decimal(paisa_total) * weight / weight_sum for weight in decimal_weights]
    floor_shares = [int(share.to_integral_value(rounding=ROUND_FLOOR)) for share in exact_shares]
    paisa_remaining = paisa_total - sum(floor_shares)
    ranked_indexes = sorted(
        range(len(exact_shares)),
        key=lambda index: (-(exact_shares[index] % 1), index),
    )
    for index in ranked_indexes[:paisa_remaining]:
        floor_shares[index] += 1

    return [
        (sign * Decimal(paisa) / 100).quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)
        for paisa in floor_shares
    ]


def _under_thousand_in_words(value: int) -> str:
    parts: list[str] = []
    remainder = value
    if remainder >= 100:
        hundreds, remainder = divmod(remainder, 100)
        parts.extend((_ONES[hundreds], "Hundred"))
    if remainder >= 20:
        tens, ones = divmod(remainder, 10)
        parts.append(_TENS[tens])
        if ones:
            parts.append(_ONES[ones])
    elif remainder:
        parts.append(_ONES[remainder])
    return " ".join(parts)


def _integer_in_words(value: int) -> str:
    if value == 0:
        return _ONES[0]
    parts: list[str] = []
    remainder = value
    for divisor, label in ((10_000_000, "Crore"), (100_000, "Lakh"), (1_000, "Thousand")):
        if remainder >= divisor:
            group, remainder = divmod(remainder, divisor)
            parts.extend((_integer_in_words(group), label))
    if remainder:
        parts.append(_under_thousand_in_words(remainder))
    return " ".join(parts)


def inr_in_words(amount: object) -> str:
    """Render rupees and paise using Indian lakh/crore number names.

    Examples:
        >>> inr_in_words("713.00")
        'Seven Hundred Thirteen Rupees Only'
        >>> inr_in_words("100000.25")
        'One Lakh Rupees And Twenty Five Paise Only'
    """
    value = money(amount)
    sign = "Minus " if value < 0 else ""
    absolute = abs(value)
    rupees = int(absolute)
    paise = int((absolute - Decimal(rupees)) * 100)
    rupee_unit = "Rupee" if rupees == 1 else "Rupees"
    words = f"{sign}{_integer_in_words(rupees)} {rupee_unit}"
    if paise:
        paisa_unit = "Paisa" if paise == 1 else "Paise"
        words = f"{words} And {_integer_in_words(paise)} {paisa_unit}"
    return f"{words} Only"


def format_inr(amount: object) -> str:
    """Format an amount with the Indian 3-2-2 grouping convention.

    Examples:
        >>> format_inr("100000")
        '₹1,00,000.00'
        >>> format_inr("-1234.5")
        '-₹1,234.50'
    """
    value = money(amount)
    prefix = "-" if value < 0 else ""
    integer_part, decimal_part = f"{abs(value):.2f}".split(".")
    if len(integer_part) <= 3:
        grouped = integer_part
    else:
        tail = integer_part[-3:]
        leading = integer_part[:-3]
        pairs: list[str] = []
        while leading:
            pairs.append(leading[-2:])
            leading = leading[:-2]
        grouped = f"{','.join(reversed(pairs))},{tail}"
    return f"{prefix}₹{grouped}.{decimal_part}"
