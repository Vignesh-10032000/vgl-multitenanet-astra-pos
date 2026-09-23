"""SQL statement instrumentation for endpoint query budgets."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import pytest
from flask import Flask
from sqlalchemy import Engine, event

from tests.api import conftest as api_fixtures
from tests.api.conftest import IdentityContext
from vglpos.extensions import db

api_app = api_fixtures.api_app
api_client = api_fixtures.api_client
api_identity = api_fixtures.api_identity
api_open_shift = api_fixtures.api_open_shift
auth_headers = api_fixtures.auth_headers
checkout_payload = api_fixtures.checkout_payload
login_payload = api_fixtures.login_payload
mutation_headers = api_fixtures.mutation_headers

QueryBudget = Callable[[int], AbstractContextManager[list[str]]]


@pytest.fixture()
def assert_max_queries(api_app: Flask) -> QueryBudget:
    """Count SQL statements within a block and fail after cleanup when over budget."""
    with api_app.app_context():
        engine: Engine = db.engine

    @contextmanager
    def budget(maximum: int) -> Iterator[list[str]]:
        statements: list[str] = []

        def count_statement(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", count_statement)
        try:
            yield statements
        finally:
            event.remove(engine, "before_cursor_execute", count_statement)
            assert len(statements) <= maximum, (
                f"query budget exceeded: {len(statements)} > {maximum}\n"
                + "\n---\n".join(statements)
            )

    return budget


__all__ = [
    "IdentityContext",
    "api_app",
    "api_client",
    "api_identity",
    "api_open_shift",
    "assert_max_queries",
    "auth_headers",
    "checkout_payload",
    "login_payload",
    "mutation_headers",
]
