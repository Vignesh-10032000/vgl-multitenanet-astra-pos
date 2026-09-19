"""Authenticated request context extraction with no body/query fallbacks."""

from __future__ import annotations

from dataclasses import dataclass

from flask import g

from vglpos.services.exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class CounterContext:
    company_id: int
    branch_id: int
    terminal_id: int
    user_id: int


def counter_context() -> CounterContext:
    """Require branch and terminal facts populated exclusively from JWT claims."""
    branch_id = getattr(g, "branch_id", None)
    terminal_id = getattr(g, "terminal_id", None)
    if branch_id is None or terminal_id is None:
        raise ValidationError("The session must select a branch and terminal.")
    return CounterContext(
        company_id=int(g.company_id),
        branch_id=int(branch_id),
        terminal_id=int(terminal_id),
        user_id=int(g.user_id),
    )
