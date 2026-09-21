"""Generate deterministic cross-engine GST fixtures for the offline PWA gate."""

from __future__ import annotations

import json
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

from vglpos.services.tax_engine import TaxEngine, TaxLineInput, TaxResult
from vglpos.utils.money import money

OUTPUT = Path(__file__).parents[1] / "tests" / "fixtures" / "tax_parity_200.json"
SEED = 6_2026
RATES = ("0.00", "0.25", "3.00", "5.00", "12.00", "18.00", "28.00", "40.00")
CESS_RATES = ("0.00", "1.00", "12.00")


def _decimal(value: int, scale: int) -> str:
    factor = 10**scale
    return f"{value // factor}.{value % factor:0{scale}d}"


def _quote(result: TaxResult) -> dict[str, Any]:
    def value(item: Decimal) -> str:
        return f"{item:.2f}"

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
            for line in result.lines
        ],
        "is_interstate": result.is_interstate,
        "gross_amount": value(result.gross_amount),
        "discount_amount": value(result.discount_amount),
        "taxable_amount": value(result.taxable_amount),
        "cgst_amount": value(result.cgst_amount),
        "sgst_amount": value(result.sgst_amount),
        "igst_amount": value(result.igst_amount),
        "cess_amount": value(result.cess_amount),
        "round_off": value(result.round_off),
        "net_amount": value(result.net_amount),
    }


def _scenario(rng: random.Random, index: int) -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    discountable = Decimal("0.00")
    for _ in range(rng.randint(1, 5)):
        quantity = _decimal(rng.randint(1, 20_000), 3)
        unit_price = _decimal(rng.randint(1, 500_000), 2)
        gross = money(Decimal(quantity) * Decimal(unit_price))
        maximum_discount = int(gross * 100)
        line_discount_paise = rng.randint(0, maximum_discount // 4) if maximum_discount else 0
        line_discount = _decimal(line_discount_paise, 2)
        discountable += gross - Decimal(line_discount)
        lines.append(
            {
                "quantity": quantity,
                "unit_price": unit_price,
                "tax_rate": rng.choice(RATES),
                "cess_rate": rng.choice(CESS_RATES),
                "line_discount": line_discount,
                "tax_inclusive": bool(rng.getrandbits(1)),
            }
        )
    maximum_order_discount = int(discountable * 100)
    order_discount = _decimal(rng.randint(0, maximum_order_discount // 5), 2)
    payload = {
        "lines": lines,
        "supplier_state": "33",
        "place_of_supply": "29" if index % 3 == 0 else "33",
        "order_discount": order_discount,
        "apply_round_off": index % 4 != 0,
    }
    result = TaxEngine.compute(
        [TaxLineInput(**line) for line in lines],
        supplier_state=payload["supplier_state"],
        place_of_supply=payload["place_of_supply"],
        order_discount=Decimal(order_discount),
        apply_round_off=payload["apply_round_off"],
    )
    return {"id": f"parity-{index:03d}", "input": payload, "expected": _quote(result)}


def main() -> None:
    """Write a reproducible corpus whose expected values come from the Python source."""
    rng = random.Random(SEED)
    payload = {
        "verification": {
            "generator": "scripts/generate_tax_parity.py",
            "source_engine": "vglpos.services.tax_engine.TaxEngine",
            "seed": SEED,
            "scenario_count": 200,
        },
        "scenarios": [_scenario(rng, index) for index in range(1, 201)],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
