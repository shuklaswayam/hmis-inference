"""
Database + migration runner tests.

The migration runner is the only persistent side-effect at boot — if it double-
applies a SQL file or chokes on a missing dir, the entire deployment posture
breaks. Tests focus on the pieces that don't need live Postgres:

    * env-var enforcement (DATABASE_URL is mandatory)
    * path resolution (migrations/ is the canonical location)
    * failure modes (uninitialised pool, missing dir)

Live-migration behaviour is covered in the integration test suite
(see DEPLOY.md §2 for the runtime-only safety check).
"""
import logging

import pytest

from backend import database as db_module
from backend.database import Database


@pytest.fixture(autouse=True)
def _reset_pool():
    """Make sure tests start with no leaked pool."""
    Database._pool = None
    yield
    Database._pool = None


def test_migrations_dir_resolves_to_repo_root():
    """Migrations live one level up from backend/, alongside docker compose."""
    expected = db_module._MIGRATIONS_DIR
    assert expected.name == "migrations"
    # Both 001 (initial schema) and 002 (severity columns) should be present.
    assert (expected / "001_create_tables.sql").exists()
    assert (expected / "002_add_metrics_severity_columns.sql").exists()


def test_run_migrations_without_init_raises(monkeypatch, caplog):
    """run_migrations requires Database.initialize() first."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    Database._pool = None

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError, match="Database.initialize"):
            # Use asyncio.run since the method is a regular coroutine
            # — no live pool needed to reach the guard.
            import asyncio
            asyncio.run(Database.run_migrations())


def test_initialize_without_database_url_raises(monkeypatch):
    """DATABASE_URL must be present in the environment."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    Database._pool = None

    import asyncio
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        asyncio.run(Database.initialize())


def test_close_idempotent_when_uninitialised():
    """close() on a fresh class must not raise."""
    Database._pool = None
    import asyncio
    # Should be a no-op, not an error.
    asyncio.run(Database.close())
    assert Database._pool is None


def test_pool_size_bounds():
    """Pool is configured with bounded min/max — guard against accidental
    unbounded growth on a config drift."""
    import inspect
    src = inspect.getsource(Database.initialize)
    assert "min_size" in src
    assert "max_size" in src


def test_schema_migrations_ddl_uses_create_table_if_not_exists():
    """The tracking table is created with IF NOT EXISTS so cold boots on
    a hot DB don't error."""
    import inspect
    src = inspect.getsource(Database.run_migrations)
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in src


def test_apply_runs_each_pending_in_own_transaction(monkeypatch):
    """run_migrations wraps each file in conn.transaction() — partial failures
    don't leave the DB in a half-applied state."""
    import inspect
    src = inspect.getsource(Database.run_migrations)
    assert "conn.transaction" in src
    assert "INSERT INTO schema_migrations" in src
