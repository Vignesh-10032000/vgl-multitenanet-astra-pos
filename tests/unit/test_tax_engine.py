"""Golden, boundary, and property tests for the pure GST engine."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vglpos.services.tax_engine import TaxEngine, TaxLineInput
from vglpos.utils.gst import (
    STATE_CODES,
    TaxRatePeriod,
    financial_year_code,
    is_interstate,
    state_code_from_gstin,
    tax_rate_for_date,
    validate_gstin,
)
from vglpos.utils.money import ZERO, money

_GOLDEN_PATH = Path(__file__).parents[1] / "fixtures" / "tax_engine_golden.json"
_EXPECTED_FIELDS = (
    "gross_amount",
    "line_discount_amount",
    "order_discount_amount",
    "discount_amount",
    "taxable_amount",
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
    "cess_amount",
    "round_off",
    "net_amount",
)


def _load_golden_scenarios() -> list[dict[str, Any]]:
    payload: dict[str, Any] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    assert payload["verification"]["method"].startswith("Hand-calculated")
    scenarios: list[dict[str, Any]] = payload["scenarios"]
    return scenarios


def _line_from_fixture(payload: dict[str, Any]) -> TaxLineInput:
    return TaxLineInput(
        quantity=payload["quantity"],
        unit_price=payload["unit_price"],
        tax_rate=payload["tax_rate"],
        line_discount=payload.get("line_discount", "0.00"),
        cess_rate=payload.get("cess_rate", "0.00"),
        tax_inclusive=payload.get("tax_inclusive", False),
    )


@pytest.mark.parametrize("scenario", _load_golden_scenarios(), ids=lambda item: item["id"])
def test_twenty_hand_calculated_golden_invoices(scenario: dict[str, Any]) -> None:
    assert len(_load_golden_scenarios()) == 20
    result = TaxEngine.compute(
        [_line_from_fixture(line) for line in scenario["lines"]],
        supplier_state=scenario["supplier_state"],
        place_of_supply=scenario["place_of_supply"],
        order_discount=Decimal(scenario["order_discount"]),
        apply_round_off=scenario["apply_round_off"],
    )

    for field in _EXPECTED_FIELDS:
        assert getattr(result, field) == Decimal(scenario["expected"][field]), field
    if "line_order_discounts" in scenario:
        assert [line.order_discount_amount for line in result.lines] == [
            Decimal(value) for value in scenario["line_order_discounts"]
        ]
    assert sum((line.order_discount_amount for line in result.lines), ZERO) == Decimal(
        scenario["order_discount"]
    )
    result.assert_reconciles()


@pytest.mark.parametrize("discount", ["0", "0.01", "50.00", "299.00"])
def test_p0_4_discounted_inclusive_invoice_always_reconciles(discount: str) -> None:
    result = TaxEngine.compute(
        [TaxLineInput("1", "299", "18", tax_inclusive=True)],
        supplier_state="33",
        place_of_supply="33",
        order_discount=Decimal(discount),
    )
    result.assert_reconciles()
    assert result.discount_amount == money(discount)


def test_mixed_rate_discount_is_apportioned_exactly() -> None:
    result = TaxEngine.compute(
        [
            TaxLineInput("1", "100", "5"),
            TaxLineInput("1", "200", "18"),
            TaxLineInput("1", "300", "40"),
        ],
        supplier_state="33",
        place_of_supply="33",
        order_discount=Decimal("73.21"),
    )
    assert sum((line.order_discount_amount for line in result.lines), ZERO) == Decimal("73.21")


def test_odd_paisa_tax_split_readds_exactly() -> None:
    result = TaxEngine.compute(
        [TaxLineInput("1", "333.33", "5")],
        supplier_state="33",
        place_of_supply="33",
        apply_round_off=False,
    )
    line = result.lines[0]
    assert line.cgst_amount == Decimal("8.33")
    assert line.sgst_amount == Decimal("8.34")
    assert line.cgst_amount + line.sgst_amount == Decimal("16.67")


@pytest.mark.parametrize(
    ("quantity", "message"),
    [
        ("-5", "greater than zero"),
        ("0", "greater than zero"),
        ("not-numeric", "quantity must be numeric"),
        ("0.0004", "at least 0.001"),
    ],
)
def test_p0_3_invalid_quantities_are_rejected(quantity: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TaxEngine.compute(
            [TaxLineInput(quantity, "10", "5")],
            supplier_state="33",
            place_of_supply="33",
        )


@pytest.mark.parametrize("rate", ["-1", "101"])
def test_p0_3_invalid_tax_rates_are_rejected(rate: str) -> None:
    with pytest.raises(ValueError, match="tax rate must be between"):
        TaxEngine.compute(
            [TaxLineInput("1", "10", rate)],
            supplier_state="33",
            place_of_supply="33",
        )


def test_p0_3_excessive_order_discount_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot exceed the order value"):
        TaxEngine.compute(
            [TaxLineInput("1", "10", "5")],
            supplier_state="33",
            place_of_supply="33",
            order_discount=Decimal("10.01"),
        )


def test_p1_2_interstate_uses_only_igst() -> None:
    result = TaxEngine.compute(
        [TaxLineInput("1", "100", "18")],
        supplier_state="33",
        place_of_supply="29",
        apply_round_off=False,
    )
    assert result.igst_amount > ZERO
    assert result.cgst_amount == result.sgst_amount == ZERO


def test_p1_2_intrastate_uses_cgst_and_sgst() -> None:
    result = TaxEngine.compute(
        [TaxLineInput("1", "100", "18")],
        supplier_state="33",
        place_of_supply="33",
        apply_round_off=False,
    )
    assert result.igst_amount == ZERO
    assert result.cgst_amount > ZERO
    assert result.sgst_amount > ZERO


@pytest.mark.parametrize(
    ("invoice_date", "expected_rate"),
    [(date(2025, 9, 20), Decimal("12")), (date(2025, 9, 25), Decimal("5"))],
)
def test_p1_3_rate_history_selects_effective_product_rate(
    invoice_date: date, expected_rate: Decimal
) -> None:
    periods = [
        TaxRatePeriod(Decimal("12"), date(2017, 7, 1), date(2025, 9, 21)),
        TaxRatePeriod(Decimal("5"), date(2025, 9, 22)),
    ]
    selected_rate = tax_rate_for_date(periods, invoice_date)
    result = TaxEngine.compute(
        [TaxLineInput("1", "100", selected_rate)],
        supplier_state="33",
        place_of_supply="33",
        apply_round_off=False,
    )
    assert result.lines[0].tax_rate == expected_rate.quantize(Decimal("0.01"))


def test_gstin_validation_checks_format_state_and_checksum() -> None:
    assert len(STATE_CODES) == 37
    assert validate_gstin(" 29aaccr7832c1zd ")
    assert not validate_gstin(29)
    assert not validate_gstin("29AACCR7832C0ZD")
    assert not validate_gstin("25AACCR7832C1ZL")
    assert not validate_gstin("29AACCR7832C1ZX")
    assert state_code_from_gstin("29AACCR7832C1ZD") == "29"
    with pytest.raises(ValueError, match="GSTIN is invalid"):
        state_code_from_gstin("invalid")


def test_financial_year_codes_april_to_march() -> None:
    assert financial_year_code(date(2026, 4, 1)) == "26-27"
    assert financial_year_code(date(2027, 3, 31)) == "26-27"


def test_supply_state_validation_and_classification() -> None:
    assert not is_interstate("33", "33")
    assert is_interstate("33", "29")
    with pytest.raises(ValueError, match="Supplier state"):
        is_interstate(33, "29")
    with pytest.raises(ValueError, match="Supplier state"):
        is_interstate("25", "29")
    with pytest.raises(ValueError, match="Place of supply"):
        is_interstate("33", "25")


def test_rate_period_selection_rejects_gap_and_overlap() -> None:
    with pytest.raises(ValueError, match="No tax rate"):
        tax_rate_for_date(
            [TaxRatePeriod(Decimal("12"), date(2020, 1, 1), date(2020, 12, 31))],
            date(2021, 1, 1),
        )
    with pytest.raises(ValueError, match="overlap"):
        tax_rate_for_date(
            [
                TaxRatePeriod(Decimal("12"), date(2020, 1, 1)),
                TaxRatePeriod(Decimal("18"), date(2020, 6, 1)),
            ],
            date(2020, 7, 1),
        )


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (TaxLineInput("1", "not-numeric", "5"), "unit price must be numeric"),
        (TaxLineInput("1", "-0.01", "5"), "unit price cannot be negative"),
        (TaxLineInput("1", "10", "bad"), "tax rate must be numeric"),
        (TaxLineInput("1", "10", "5", cess_rate="bad"), "cess rate must be numeric"),
        (TaxLineInput("1", "10", "5", cess_rate="-1"), "cess rate must be between"),
        (TaxLineInput("1", "10", "5", cess_rate="101"), "cess rate must be between"),
        (TaxLineInput("1", "10", "5", line_discount="bad"), "line discount must be numeric"),
        (TaxLineInput("1", "10", "5", line_discount="-1"), "line discount cannot be negative"),
        (TaxLineInput("1", "10", "5", line_discount="10.01"), "cannot exceed line gross"),
        (TaxLineInput("1", "10", "5", tax_inclusive="yes"), "flag must be boolean"),
    ],
)
def test_line_failure_paths_have_specific_messages(line: TaxLineInput, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TaxEngine.compute([line], supplier_state="33", place_of_supply="33")


def test_invoice_level_failure_paths_have_specific_messages() -> None:
    with pytest.raises(ValueError, match="At least one tax line"):
        TaxEngine.compute([], supplier_state="33", place_of_supply="33")
    with pytest.raises(ValueError, match="Apply-round-off flag"):
        TaxEngine.compute(
            [TaxLineInput("1", "10", "5")],
            supplier_state="33",
            place_of_supply="33",
            apply_round_off="yes",
        )
    with pytest.raises(ValueError, match="Order discount must be numeric"):
        TaxEngine.compute(
            [TaxLineInput("1", "10", "5")],
            supplier_state="33",
            place_of_supply="33",
            order_discount="bad",
        )
    with pytest.raises(ValueError, match="Order discount cannot be negative"):
        TaxEngine.compute(
            [TaxLineInput("1", "10", "5")],
            supplier_state="33",
            place_of_supply="33",
            order_discount=Decimal("-0.01"),
        )


def test_reconciliation_guard_detects_corruption_and_allows_one_paisa_tolerance() -> None:
    result = TaxEngine.compute(
        [TaxLineInput("1", "100", "5")],
        supplier_state="33",
        place_of_supply="33",
        apply_round_off=False,
    )
    replace(result, net_amount=result.net_amount + Decimal("0.01")).assert_reconciles()
    with pytest.raises(ValueError, match="Invoice does not reconcile"):
        replace(result, net_amount=result.net_amount + Decimal("0.02")).assert_reconciles()


@st.composite
def _cart_and_discount(draw: st.DrawFn) -> tuple[list[TaxLineInput], Decimal]:
    raw_lines = draw(
        st.lists(
            st.tuples(
                st.decimals(min_value="0.001", max_value="100", places=3),
                st.decimals(min_value="0", max_value="10000", places=2),
                st.sampled_from([Decimal("0"), Decimal("5"), Decimal("18"), Decimal("40")]),
                st.booleans(),
            ),
            min_size=1,
            max_size=50,
        )
    )
    lines = [
        TaxLineInput(quantity, price, rate, tax_inclusive=inclusive)
        for quantity, price, rate, inclusive in raw_lines
    ]
    total = sum((money(quantity * price) for quantity, price, _, _ in raw_lines), ZERO)
    discount_paisa = draw(st.integers(min_value=0, max_value=int(total * 100)))
    return lines, Decimal(discount_paisa) / 100


@settings(max_examples=1000, deadline=None)
@given(_cart_and_discount(), st.booleans())
def test_random_carts_always_reconcile(
    case: tuple[list[TaxLineInput], Decimal], interstate: bool
) -> None:
    lines, discount = case
    result = TaxEngine.compute(
        lines,
        supplier_state="33",
        place_of_supply="29" if interstate else "33",
        order_discount=discount,
    )
    result.assert_reconciles()
    assert sum((line.order_discount_amount for line in result.lines), ZERO) == discount


def test_non_test_sources_never_construct_binary_floats() -> None:
    source_root = Path(__file__).parents[2] / "src" / "vglpos"
    source_files = [
        *(source_root / "utils").glob("*.py"),
        source_root / "services" / "tax_engine.py",
    ]
    offenders = [str(path) for path in source_files if "float(" in path.read_text(encoding="utf-8")]
    assert offenders == []
