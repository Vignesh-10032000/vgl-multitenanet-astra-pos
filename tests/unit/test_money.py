"""Exhaustive unit and property tests for exact money helpers."""

from __future__ import annotations

import doctest
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vglpos.utils import money as money_module
from vglpos.utils.money import (
    ZERO,
    apportion,
    format_inr,
    inr_in_words,
    money,
    qty,
    round_off_to_rupee,
    to_decimal,
)


def test_money_doc_examples_are_executable() -> None:
    failures, _ = doctest.testmod(money_module)
    assert failures == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("7.25"), Decimal("7.25")),
        (7, Decimal("7")),
        (" 7.25 ", Decimal("7.25")),
        (0.1, Decimal("0.1")),
    ],
)
def test_to_decimal_uses_exact_input_boundary(value: object, expected: Decimal) -> None:
    assert to_decimal(value) == expected


@pytest.mark.parametrize(
    "value",
    [True, "", "not-a-number", object(), Decimal("NaN"), Decimal("Infinity")],
)
def test_to_decimal_rejects_non_decimal_values(value: object) -> None:
    with pytest.raises(ValueError, match="finite decimal"):
        to_decimal(value)


def test_money_and_quantity_round_half_up() -> None:
    assert money("1.005") == Decimal("1.01")
    assert money("-1.005") == Decimal("-1.01")
    assert qty("1.2345") == Decimal("1.235")
    assert qty("-1.2345") == Decimal("-1.235")


def test_quantizers_report_values_outside_decimal_context() -> None:
    huge = Decimal("1E+999999")
    with pytest.raises(ValueError, match="Money value is outside"):
        money(huge)
    with pytest.raises(ValueError, match="Quantity is outside"):
        qty(huge)


@pytest.mark.parametrize(
    ("value", "expected_total", "expected_delta"),
    [
        ("10.49", "10.00", "-0.49"),
        ("10.50", "11.00", "0.50"),
        ("-10.50", "-11.00", "-0.50"),
    ],
)
def test_round_off_to_rupee_records_signed_delta(
    value: str, expected_total: str, expected_delta: str
) -> None:
    assert round_off_to_rupee(value) == (
        Decimal(expected_total),
        Decimal(expected_delta),
    )


def test_apportion_uses_largest_remainder_and_stable_ties() -> None:
    assert apportion("0.05", [1, 1, 1]) == [
        Decimal("0.02"),
        Decimal("0.02"),
        Decimal("0.01"),
    ]
    assert apportion("10.00", [0, 1, 3]) == [
        Decimal("0.00"),
        Decimal("2.50"),
        Decimal("7.50"),
    ]


def test_apportion_supports_zero_and_negative_totals() -> None:
    assert apportion(ZERO, []) == []
    assert apportion(ZERO, [0, 0]) == [ZERO, ZERO]
    assert apportion("-0.05", [1, 1, 1]) == [
        Decimal("-0.02"),
        Decimal("-0.02"),
        Decimal("-0.01"),
    ]


def test_apportion_rejects_impossible_weights() -> None:
    with pytest.raises(ValueError, match="At least one weight"):
        apportion("1.00", [])
    with pytest.raises(ValueError, match="cannot be negative"):
        apportion("1.00", [1, -1])
    with pytest.raises(ValueError, match="positive value"):
        apportion("1.00", [0, 0])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", "Zero Rupees Only"),
        ("1", "One Rupee Only"),
        ("0.01", "Zero Rupees And One Paisa Only"),
        ("15.25", "Fifteen Rupees And Twenty Five Paise Only"),
        ("20", "Twenty Rupees Only"),
        ("100", "One Hundred Rupees Only"),
        ("713", "Seven Hundred Thirteen Rupees Only"),
        ("1001", "One Thousand One Rupees Only"),
        ("100001", "One Lakh One Rupees Only"),
        ("10000000", "One Crore Rupees Only"),
        ("-21000001", "Minus Two Crore Ten Lakh One Rupees Only"),
    ],
)
def test_inr_in_words_uses_indian_numbering(value: str, expected: str) -> None:
    assert inr_in_words(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12.3", "₹12.30"),
        ("1234.50", "₹1,234.50"),
        ("100000", "₹1,00,000.00"),
        ("123456789.12", "₹12,34,56,789.12"),
        ("-1234.5", "-₹1,234.50"),
    ],
)
def test_format_inr_uses_indian_digit_groups(value: str, expected: str) -> None:
    assert format_inr(value) == expected


@settings(max_examples=1000, deadline=None)
@given(st.decimals(min_value="-1000000000", max_value="1000000000", places=6))
def test_money_is_idempotent(value: Decimal) -> None:
    assert money(money(value)) == money(value)


@settings(max_examples=1000, deadline=None)
@given(
    total=st.decimals(min_value="-100000", max_value="100000", places=2),
    weights=st.lists(
        st.decimals(min_value="0", max_value="10000", places=3),
        min_size=1,
        max_size=30,
    ).filter(lambda values: any(value > 0 for value in values)),
)
def test_apportion_always_sums_exactly(total: Decimal, weights: list[Decimal]) -> None:
    assert sum(apportion(total, weights), ZERO) == money(total)
