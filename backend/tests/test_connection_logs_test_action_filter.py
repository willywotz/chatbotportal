"""Test-action visibility on GET /connection-logs and /information."""
from app.features.agency.models.agency import AgencyStatus
from app.features.agency.repositories import agency as agency_repo
from app.core.repositories import connection_log as connection_log_repo


async def _seed_one_each(session, ag):
    await connection_log_repo.create(session, agency_id=ag.id, connection_type="API", status="success", action="test")
    await connection_log_repo.create(session, agency_id=ag.id, connection_type="API", status="success", action="query")


async def test_test_action_hidden_by_default(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status=AgencyStatus.active)
    await _seed_one_each(db_session, ag)
    r = await client.get("/api/v1/connection-logs")
    body = r.json()
    assert [i["action"] for i in body["items"]] == ["query"]
    assert body["total_items"] == 1
    assert body["total_connections"] == 1
    assert body["successful_connections"] == 1


async def test_include_test_shows_all(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status=AgencyStatus.active)
    await _seed_one_each(db_session, ag)
    r = await client.get("/api/v1/connection-logs", params={"include_test": True})
    body = r.json()
    assert body["total_items"] == 2
    assert body["total_connections"] == 2
    assert {i["action"] for i in body["items"]} == {"test", "query"}


async def test_info_excludes_test_by_default(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status=AgencyStatus.active)
    await _seed_one_each(db_session, ag)
    default = (await client.get("/api/v1/connection-logs/information")).json()
    with_test = (await client.get("/api/v1/connection-logs/information", params={"include_test": True})).json()
    assert default["total_connections"] == 1
    assert with_test["total_connections"] == 2
