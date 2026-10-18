"""Protect concurrent browser requests from sharing one SQLite cursor."""

from sqlalchemy.pool import StaticPool

from vglpos.config import TestingConfig


def test_db_01_file_sqlite_uses_separate_connections_for_parallel_requests() -> None:
    config = TestingConfig(TEST_DATABASE_URL="sqlite+pysqlite:///disposable_test.db")
    assert "poolclass" not in config._engine_options()
    assert config._engine_options()["connect_args"]["check_same_thread"] is False


def test_db_02_memory_sqlite_preserves_one_shared_database() -> None:
    assert TestingConfig()._engine_options()["poolclass"] is StaticPool
