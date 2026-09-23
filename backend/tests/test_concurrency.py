import asyncio
import logging

from app.core.concurrency import spawn_logged


async def test_spawn_logged_runs_coro():
    done = asyncio.Event()

    async def work():
        done.set()

    spawn_logged(work(), name="work")
    await asyncio.wait_for(done.wait(), timeout=1)


async def test_spawn_logged_logs_exception(caplog):
    async def boom():
        raise ValueError("kaboom")

    with caplog.at_level(logging.ERROR, logger="app.core.concurrency"):
        spawn_logged(boom(), name="boom")
        await asyncio.sleep(0.05)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("boom" in r.getMessage() and "kaboom" in str(r.exc_info or r.getMessage())
               or "boom" in r.getMessage() for r in errors)
