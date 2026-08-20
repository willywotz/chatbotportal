from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)

from app.config import connect_args, database_url, settings

engine = create_async_engine(
    database_url(settings),
    connect_args=connect_args(settings),
    pool_size=settings.DB_POOL_MAX,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped session; the dependency owns one transaction.

    Commit-on-success, rollback-on-exception. Callers never commit.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session


async def close_db() -> None:
    await engine.dispose()


# Fixed 64-bit key for the migration advisory lock. Arbitrary but constant:
# every worker/process must ask for the same key to serialize on it.
_MIGRATION_LOCK_KEY = 728123456789


async def run_migrations() -> None:
    """Run Alembic migrations to head, serialized across workers.

    Multiple uvicorn workers call `init_db()` -> `run_migrations()`
    concurrently on startup against the same fresh database. Without
    serialization, concurrent `CREATE TABLE`/`CREATE TYPE` statements race on
    Postgres's catalog (`UniqueViolationError`) or deadlock. A session-level
    Postgres advisory lock, held on its own connection, makes every caller
    but one block; the rest then find the database already at head (no-op).
    """
    import asyncio

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _MIGRATION_LOCK_KEY})
        try:
            cfg = Config("alembic.ini")
            cfg.set_main_option("sqlalchemy.url", database_url(settings))
            await asyncio.to_thread(command.upgrade, cfg, "head")
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _MIGRATION_LOCK_KEY})


async def init_db() -> None:
    await run_migrations()

    from app.services.llm.seed import seed_llm_defaults

    async with AsyncSessionLocal() as session, session.begin():
        await seed_llm_defaults(session)
