"""Shift persistence queries."""

from __future__ import annotations

from vglpos.domain.models import Shift
from vglpos.repositories.base import BaseRepository


class ShiftRepository(BaseRepository[Shift]):
    """Query cash-drawer shifts within one company."""

    model = Shift

    def find_open(self, terminal_id: int, *, for_update: bool = False) -> Shift | None:
        """Find the open shift for a terminal and optionally lock it."""
        statement = self._base_query().where(
            Shift.terminal_id == terminal_id,
            Shift.status == "OPEN",
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)
