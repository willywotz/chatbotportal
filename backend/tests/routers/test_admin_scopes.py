"""HTTP-level scope enforcement for audit-log, connection-logs, settings, and
the llm:read/llm:write split. One deny + one allow case per file, mirroring
tests/routers/test_staff_dashboard_scopes.py.
"""

_NO_ADMIN_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


async def test_audit_log_denied_without_scope(client, as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    r = await client.get("/api/v1/audit-log/")
    assert r.status_code == 403


async def test_audit_log_allowed_with_scope(client, as_principal):
    as_principal(role="staff", scopes=["audit:read"])
    r = await client.get("/api/v1/audit-log/")
    assert r.status_code == 200


async def test_connection_logs_denied_without_scope(client, as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    r = await client.get("/api/v1/connection-logs")
    assert r.status_code == 403


async def test_connection_logs_allowed_with_scope(client, as_principal):
    as_principal(role="staff", scopes=["connlog:read"])
    r = await client.get("/api/v1/connection-logs")
    assert r.status_code == 200


async def test_settings_denied_without_scope(client, as_principal):
    as_principal(role="user", scopes=_NO_ADMIN_SCOPES)
    r = await client.get("/api/v1/settings")
    assert r.status_code == 403


async def test_settings_allowed_with_scope(client, as_principal):
    as_principal(role="staff", scopes=["settings:read"])
    r = await client.get("/api/v1/settings")
    assert r.status_code == 200


async def test_settings_write_needs_settings_write_scope(client, as_principal):
    as_principal(role="staff", scopes=["settings:read"])
    r = await client.put("/api/v1/settings", json={"settings": []})
    assert r.status_code == 403


async def test_llm_read_scope_can_get_but_not_post(client, as_principal):
    as_principal(role="staff", scopes=["llm:read"])
    get_resp = await client.get("/api/v1/language-model/providers")
    post_resp = await client.post(
        "/api/v1/language-model/providers",
        json={"name": "p", "base_url": "https://p.example"},
    )
    assert get_resp.status_code == 200
    assert post_resp.status_code == 403


async def test_llm_write_scope_allows_post(client, as_principal):
    as_principal(role="staff", scopes=["llm:write"])
    r = await client.post(
        "/api/v1/language-model/providers",
        json={"name": "p2", "base_url": "https://p2.example"},
    )
    assert r.status_code == 201
