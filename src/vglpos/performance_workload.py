"""Shared topology for the disposable multi-cashier load dataset and Locust."""

from __future__ import annotations

from dataclasses import dataclass

PRODUCT_COUNT = 5_000
SCANS_PER_SALE = 5


@dataclass(frozen=True, slots=True)
class PerformanceLane:
    username: str
    branch_id: int
    terminal_id: int
    barcodes: tuple[str, ...]


def lane_for_index(
    index: int,
    count: int,
    *,
    username: str,
    first_branch_id: int,
    first_terminal_id: int,
) -> PerformanceLane:
    """Give each cashier independent fiscal and stock rows, not one lock convoy."""
    if not 1 <= count <= PRODUCT_COUNT // SCANS_PER_SALE:
        raise ValueError("Cashier count must fit the seeded product catalogue.")
    if not 0 <= index < count:
        raise ValueError("Cashier lane index is outside the seeded range.")
    first_barcode = index * SCANS_PER_SALE + 1
    return PerformanceLane(
        username=username if count == 1 else f"{username}-{index + 1:03d}",
        branch_id=first_branch_id + index,
        terminal_id=first_terminal_id + index,
        barcodes=tuple(
            f"PERF-{product_id:05d}"
            for product_id in range(first_barcode, first_barcode + SCANS_PER_SALE)
        ),
    )
