"""Pure GST jurisdiction and identifier helpers.

The GSTIN checksum is the base-36 Luhn variant used by the GST system. Format-only
validation is insufficient because it accepts most transcription errors.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from vglpos.domain.reference import STATE_CODES as REFERENCE_STATE_CODES
from vglpos.utils.money import to_decimal

STATE_CODES: dict[str, str] = dict(REFERENCE_STATE_CODES)

_GSTIN_PATTERN: Final = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_BASE36: Final = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True, slots=True)
class TaxRatePeriod:
    """Describe one dated tax-rate interval for historical invoice selection."""

    rate: Decimal
    effective_from: date
    effective_to: date | None = None


def _gstin_check_character(body: str) -> str:
    factor = 1
    total = 0
    for character in body:
        product = factor * _BASE36.index(character)
        total += (product // 36) + (product % 36)
        factor = 2 if factor == 1 else 1
    return _BASE36[(36 - (total % 36)) % 36]


def validate_gstin(gstin: object) -> bool:
    """Validate GSTIN structure, current state code, and checksum.

    Input is normalized to uppercase so identifiers copied from case-insensitive forms do
    not fail unnecessarily; embedded whitespace remains invalid.
    """
    if not isinstance(gstin, str):
        return False
    normalized = gstin.strip().upper()
    if _GSTIN_PATTERN.fullmatch(normalized) is None:
        return False
    if normalized[:2] not in STATE_CODES:
        return False
    return _gstin_check_character(normalized[:-1]) == normalized[-1]


def state_code_from_gstin(gstin: object) -> str:
    """Return a verified GSTIN's jurisdiction code rather than trusting its prefix."""
    if not validate_gstin(gstin):
        raise ValueError("GSTIN is invalid.")
    assert isinstance(gstin, str)
    return gstin.strip()[:2]


def financial_year_code(value: date) -> str:
    """Return the two-year Indian financial-year code used on fiscal documents.

    Examples:
        >>> financial_year_code(date(2026, 4, 1))
        '26-27'
        >>> financial_year_code(date(2027, 3, 31))
        '26-27'
    """
    starting_year = value.year if value.month >= 4 else value.year - 1
    return f"{starting_year % 100:02d}-{(starting_year + 1) % 100:02d}"


def _validated_state_code(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a valid GST state code.")
    normalized = value.strip()
    if normalized not in STATE_CODES:
        raise ValueError(f"{label} must be a valid GST state code.")
    return normalized


def is_interstate(supplier_state: object, place_of_supply: object) -> bool:
    """Classify supply only after both GST jurisdiction codes are validated."""
    supplier = _validated_state_code(supplier_state, "Supplier state")
    destination = _validated_state_code(place_of_supply, "Place of supply")
    return supplier != destination


def tax_rate_for_date(periods: Sequence[TaxRatePeriod], on_date: date) -> Decimal:
    """Select exactly one effective rate so historical bills retain their original tax.

    Overlapping periods are rejected instead of silently choosing a rate. The caller owns
    the product-specific mapping between old and new slabs; this helper only enforces dated
    schedule selection.
    """
    matches = [
        period
        for period in periods
        if period.effective_from <= on_date
        and (period.effective_to is None or on_date <= period.effective_to)
    ]
    if not matches:
        raise ValueError("No tax rate is effective on the requested date.")
    if len(matches) > 1:
        raise ValueError("Tax-rate periods overlap on the requested date.")
    return to_decimal(matches[0].rate)
