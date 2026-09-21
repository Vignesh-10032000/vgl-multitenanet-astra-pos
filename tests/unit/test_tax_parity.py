"""Lock the generated shared corpus to the authoritative Python GST engine."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from vglpos.services.tax_engine import TaxEngine, TaxLineInput

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tax_parity_200.json"


def _expected(result: object) -> dict[str, Any]:
    tax = result
    value = lambda amount: f"{amount:.2f}"  # noqa: E731
    return {
        "lines": [
            {
                "quantity": f"{line.quantity:.3f}",
                "unit_price": value(line.unit_price),
                "gross_amount": value(line.gross_amount),
                "discount_amount": value(line.discount_amount),
                "taxable_amount": value(line.taxable_amount),
                "tax_rate": value(line.tax_rate),
                "cess_rate": value(line.cess_rate),
                "cgst_amount": value(line.cgst_amount),
                "sgst_amount": value(line.sgst_amount),
                "igst_amount": value(line.igst_amount),
                "cess_amount": value(line.cess_amount),
                "total_amount": value(line.line_total),
            }
            for line in tax.lines
        ],
        "is_interstate": tax.is_interstate,
        "gross_amount": value(tax.gross_amount),
        "discount_amount": value(tax.discount_amount),
        "taxable_amount": value(tax.taxable_amount),
        "cgst_amount": value(tax.cgst_amount),
        "sgst_amount": value(tax.sgst_amount),
        "igst_amount": value(tax.igst_amount),
        "cess_amount": value(tax.cess_amount),
        "round_off": value(tax.round_off),
        "net_amount": value(tax.net_amount),
    }


def test_shared_tax_parity_corpus_matches_python_engine() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["verification"]["scenario_count"] == 200
    assert len(payload["scenarios"]) == 200
    for scenario in payload["scenarios"]:
        inputs = scenario["input"]
        result = TaxEngine.compute(
            [TaxLineInput(**line) for line in inputs["lines"]],
            supplier_state=inputs["supplier_state"],
            place_of_supply=inputs["place_of_supply"],
            order_discount=Decimal(inputs["order_discount"]),
            apply_round_off=inputs["apply_round_off"],
        )
        assert _expected(result) == scenario["expected"], scenario["id"]
