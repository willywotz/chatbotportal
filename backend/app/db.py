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


async def run_migrations() -> None:
    import asyncio

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url(settings))
    await asyncio.to_thread(command.upgrade, cfg, "head")


async def init_db() -> None:
    await run_migrations()

    from app.services.llm.seed import seed_llm_defaults

    async with AsyncSessionLocal() as session, session.begin():
        await seed_llm_defaults(session)
