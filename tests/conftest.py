"""Shared pytest fixtures.

The suite never touches a real database: TestingConfig defaults to in-memory
SQLite, and an autouse guard fails the run loudly if the engine ever points
anywhere else. All database work in a test happens inside a connection-level
transaction that is rolled back after every test.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from vglpos.app import create_app
from vglpos.config import TestingConfig
from vglpos.extensions import db


@pytest.fixture(scope="session")
def app() -> Flask:
    """Application built by passing TestingConfig INTO the factory.

    WHY explicit: relying on APP_ENV here would recreate the P0-6 bug class —
    an app configured after (or differently from) what the test believes.
    """
    return create_app(TestingConfig)


@pytest.fixture(autouse=True)
def _assert_test_database(app: Flask) -> None:
    """Refuse to run ANY test whose engine is not a disposable test database."""
    with app.app_context():
        url = db.engine.url
    is_memory_sqlite = url.get_backend_name() == "sqlite" and url.database in (None, ":memory:")
    is_named_test_db = (url.database or "").endswith("_test")
    if not (app.config.get("TESTING") is True and (is_memory_sqlite or is_named_test_db)):
        pytest.fail(
            "SAFETY: refusing to run tests against "
            f"{url.render_as_string(hide_password=True)!r}. Tests require TESTING=True and "
            "either in-memory SQLite or a database whose name ends in '_test' "
            "(set via TEST_DATABASE_URL)."
        )


@pytest.fixture()
def db_session(app: Flask) -> Generator[scoped_session[Session], None, None]:
    """Session bound to an outer connection-level transaction.

    The session joins via SAVEPOINT (``join_transaction_mode="create_savepoint"``),
    so code under test may commit freely — commits only release savepoints — and
    the outer transaction is rolled back after every test, leaving the database
    untouched no matter what the test did.
    """
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()
        factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
        session: scoped_session[Session] = scoped_session(factory)
        original_session = db.session
        db.session = session  # type: ignore[assignment]
        try:
            yield session
        finally:
            db.session = original_session  # type: ignore[assignment]
            session.remove()
            transaction.rollback()
            connection.close()


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    """Plain test client; requests run through the full middleware stack."""
    return app.test_client()
