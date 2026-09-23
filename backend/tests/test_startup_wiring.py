import pytest

pytestmark = pytest.mark.asyncio


async def test_init_db_runs_migrations_then_seeds(monkeypatch):
    import app.db as db
    calls = []

    async def _fake_migrations():
        calls.append("migrate")

    async def _fake_ensure_key(*args, **kwargs):
        calls.append("signing-key")

    async def _fake_seed(session):
        calls.append("seed-llm")

    async def _fake_seed_admin(session):
        calls.append("seed-admin")

    monkeypatch.setattr(db, "run_migrations", _fake_migrations)
    monkeypatch.setattr("app.auth.oidc.keys.ensure_signing_key", _fake_ensure_key)
    monkeypatch.setattr("app.services.llm.seed.seed_llm_defaults", _fake_seed)
    monkeypatch.setattr("app.services.user_seed.seed_admin_user", _fake_seed_admin)
    await db.init_db()
    # migrations first, then the signing key, then the DB seeds; no generate_schemas
    assert calls == ["migrate", "signing-key", "seed-llm", "seed-admin"]
