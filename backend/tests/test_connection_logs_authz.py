"""Non-admin callers must be denied `connlog:read`-scoped connection-logs routes.

Pins the deny path at the HTTP layer, mirroring tests/test_connection_logs_filter.py.
"""
_NO_ADMIN_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


async def test_non_admin_denied_list_connection_logs(client, as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    r = await client.get("/api/v1/connection-logs")
    assert r.status_code == 403


async def test_admin_allowed_list_connection_logs(client, as_principal):
    as_principal()
    r = await client.get("/api/v1/connection-logs")
    assert r.status_code == 200
    assert r.json()["total_items"] == 0


async def test_non_admin_denied_connection_log_info(client, as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    r = await client.get("/api/v1/connection-logs/information")
    assert r.status_code == 403


async def test_admin_allowed_connection_log_info(client, as_principal):
    as_principal()
    r = await client.get("/api/v1/connection-logs/information")
    assert r.status_code == 200
    assert r.json()["total_connections"] == 0
