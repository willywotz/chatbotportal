"""Characterization + new-filter tests for GET /connection-logs."""
from app.features.agency.models.agency import AgencyStatus
from app.features.agency.repositories import agency as agency_repo
from app.core.repositories import connection_log as connection_log_repo


async def test_connection_logs_paginate_unchanged(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status=AgencyStatus.active)
    for _ in range(5):
        await connection_log_repo.create(db_session, agency_id=ag.id, connection_type="API", status="success", action="test")
    r = await client.get("/api/v1/connection-logs", params={"page": 1, "limit": 2, "include_test": True})
    body = r.json()
    assert len(body["items"]) == 2            # CURRENT behavior — pinned
    assert body["total_items"] == 5


async def test_status_and_type_filters_apply_to_items_and_stats(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status=AgencyStatus.active)
    await connection_log_repo.create(db_session, agency_id=ag.id, connection_type="API", status="success", action="test")
    await connection_log_repo.create(db_session, agency_id=ag.id, connection_type="API", status="error", action="test")
    await connection_log_repo.create(db_session, agency_id=ag.id, connection_type="MCP", status="success", action="test")
    r = await client.get("/api/v1/connection-logs",
                         params={"status": "success", "connection_type": "API", "include_test": True})
    body = r.json()
    assert len(body["items"]) == 1
    assert body["total_items"] == 1
    assert body["successful_connections"] == 1  # stats reflect the filter too
    assert body["failed_connections"] == 0


async def test_page_size_alias_for_limit(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status=AgencyStatus.active)
    for _ in range(4):
        await connection_log_repo.create(db_session, agency_id=ag.id, connection_type="API", status="success", action="test")
    r = await client.get("/api/v1/connection-logs", params={"page_size": 2, "include_test": True})
    assert len(r.json()["items"]) == 2
