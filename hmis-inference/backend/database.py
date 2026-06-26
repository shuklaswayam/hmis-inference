"""
PostgreSQL connection pool with idempotent migration runner.

Adds a lightweight schema-tracking table (``schema_migrations``) and applies
any ``*.sql`` files in ``migrations/`` that have not been applied yet.
Safe to call on every boot — re-running does nothing.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import asyncpg
from asyncpg.pool import Pool

logger = logging.getLogger(__name__)

# ``backend/database.py`` -> ``migrations/`` lives one level up
# (the project root). parents[1] from the file's directory is the root.
_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


class Database:
    _pool: Pool | None = None

    @classmethod
    async def initialize(cls) -> None:
        if cls._pool is None:
            dsn = os.environ.get("DATABASE_URL")
            if not dsn:
                raise RuntimeError("DATABASE_URL environment variable is not set")
            cls._pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            logger.info("Database pool initialised")

    @classmethod
    async def close(cls) -> None:
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

    @classmethod
    @asynccontextmanager
    async def acquire(cls) -> AsyncGenerator[asyncpg.Connection, None]:
        if cls._pool is None:
            await cls.initialize()
        async with cls._pool.acquire() as conn:
            yield conn

    @classmethod
    async def execute(cls, query: str, *args) -> str:
        async with cls.acquire() as conn:
            return await conn.execute(query, *args)

    @classmethod
    async def fetch(cls, query: str, *args) -> list[asyncpg.Record]:
        async with cls.acquire() as conn:
            return await conn.fetch(query, *args)

    @classmethod
    async def fetchrow(cls, query: str, *args) -> asyncpg.Record | None:
        async with cls.acquire() as conn:
            return await conn.fetchrow(query, *args)

    @classmethod
    async def fetchval(cls, query: str, *args) -> any:
        async with cls.acquire() as conn:
            return await conn.fetchval(query, *args)

    # -----------------------------------------------------------------------
    # Migrations
    # -----------------------------------------------------------------------
    @classmethod
    async def run_migrations(cls) -> list[str]:
        """Apply any unapplied ``*.sql`` files in ``migrations/`` in order.

        Idempotent — tracks applied filenames in the ``schema_migrations``
        table and only runs new ones. Returns the list of filenames applied
        during this boot.
        """
        if cls._pool is None:
            raise RuntimeError(
                "Database.initialize() must be called before run_migrations()"
            )
        if not _MIGRATIONS_DIR.exists():
            logger.info("No migrations directory at %s — skipping", _MIGRATIONS_DIR)
            return []

        async with cls._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            applied = {
                row["filename"]
                for row in await conn.fetch(
                    "SELECT filename FROM schema_migrations"
                )
            }

        pending = sorted(
            path
            for path in _MIGRATIONS_DIR.glob("*.sql")
            if path.name not in applied
        )

        for path in pending:
            sql = path.read_text()
            async with cls._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (filename) VALUES ($1)",
                        path.name,
                    )
            logger.info("Applied migration: %s (%d bytes)", path.name, len(sql))

        return [p.name for p in pending]
