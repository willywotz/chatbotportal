from sqlalchemy.ext.asyncio import AsyncEngine
from app.db import engine, AsyncSessionLocal, get_db


def test_engine_uses_asyncpg_and_no_expire_on_commit():
    assert isinstance(engine, AsyncEngine)
    assert engine.url.drivername == "postgresql+asyncpg"
    assert AsyncSessionLocal.kw["expire_on_commit"] is False


def test_get_db_is_async_generator_callable():
    import inspect
    assert inspect.isasyncgenfunction(get_db)
