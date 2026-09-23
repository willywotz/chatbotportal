import pytest

pytestmark = pytest.mark.asyncio


async def test_init_db_runs_migrations_then_seeds(monkeypatch):
    import app.db as db
    calls = []

    async def _fake_migrations():
        calls.append("migrate")

    async def _fake_seed(session):
        calls.append("seed")

    monkeypatch.setattr(db, "run_migrations", _fake_migrations)
    monkeypatch.setattr("app.services.llm.seed.seed_llm_defaults", _fake_seed)
    await db.init_db()
    assert calls == ["migrate", "seed"]  # migrations first, then seed; no generate_schemas
