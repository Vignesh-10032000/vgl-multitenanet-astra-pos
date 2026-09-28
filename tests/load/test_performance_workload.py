"""The 150-cashier gate must exercise distinct checkout lock domains."""

from __future__ import annotations

import pytest

from vglpos.performance_workload import lane_for_index


def test_150_cashiers_have_distinct_branches_terminals_users_and_products() -> None:
    lanes = [
        lane_for_index(
            index,
            150,
            username="cashier",
            first_branch_id=1,
            first_terminal_id=1,
        )
        for index in range(150)
    ]
    assert len({lane.username for lane in lanes}) == 150
    assert len({lane.branch_id for lane in lanes}) == 150
    assert len({lane.terminal_id for lane in lanes}) == 150
    assert len({barcode for lane in lanes for barcode in lane.barcodes}) == 750
    assert lanes[0].barcodes == tuple(f"PERF-{index:05d}" for index in range(1, 6))
    assert lanes[-1].barcodes == tuple(f"PERF-{index:05d}" for index in range(746, 751))


def test_single_cashier_keeps_existing_fixture_names() -> None:
    lane = lane_for_index(
        0,
        1,
        username="cashier",
        first_branch_id=1,
        first_terminal_id=1,
    )
    assert lane.username == "cashier"
    assert (lane.branch_id, lane.terminal_id) == (1, 1)


@pytest.mark.parametrize("index,count", [(-1, 150), (150, 150), (0, 0), (0, 1_001)])
def test_invalid_lane_is_rejected(index: int, count: int) -> None:
    with pytest.raises(ValueError):
        lane_for_index(
            index,
            count,
            username="cashier",
            first_branch_id=1,
            first_terminal_id=1,
        )
