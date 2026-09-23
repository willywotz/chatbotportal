"""Multiple uvicorn workers call `run_migrations()` concurrently against the
same fresh database on startup. Without serialization, concurrent
`CREATE TABLE`/`CREATE TYPE` statements race on Postgres's catalog and raise
`UniqueViolationError`. `run_migrations()` must hold a Postgres advisory lock
so only one caller runs `alembic upgrade head` at a time; the rest block,
then find the database already at head (no-op).
"""

import asyncio
import uuid
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


@pytest_asyncio.fixture
async def fresh_database_url(pg_container):
    """A throwaway, unmigrated database on the shared testcontainer."""
    admin_dsn = pg_container.get_connection_url(driver=None)
    db_name = f"migration_race_{uuid.uuid4().hex[:8]}"
    admin_conn = await asyncpg.connect(dsn=admin_dsn)
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

    fresh_dsn = urlunparse(urlparse(admin_dsn)._replace(path=f"/{db_name}"))
    yield fresh_dsn

    admin_conn = await asyncpg.connect(dsn=admin_dsn)
    try:
        await admin_conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            db_name,
        )
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await admin_conn.close()


async def test_run_migrations_concurrent_is_race_safe(fresh_database_url):
    import app.db as db_module
    from app.config import database_url, settings

    original_url, original_engine = settings.DATABASE_URL, db_module.engine
    settings.DATABASE_URL = fresh_database_url
    db_module.engine = create_async_engine(database_url(settings), poolclass=NullPool)
    try:
        results = await asyncio.gather(
            db_module.run_migrations(), db_module.run_migrations(),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, Exception)]
        assert not errors, errors

        async with db_module.engine.connect() as conn:
            version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        assert version is not None
    finally:
        await db_module.engine.dispose()
        db_module.engine, settings.DATABASE_URL = original_engine, original_url
