"""HTTP-level scope enforcement for GET/POST /api/v1/agencies.

A plain `user` role carrying only `agency:list` may browse the list (the
Architecture page) but must not create an agency; `agency:write` is required
for that.
"""


async def test_list_agencies_allowed_with_agency_list_scope(client, as_principal):
    as_principal(role="user", scopes=["agency:list"])
    r = await client.get("/api/v1/agencies")
    assert r.status_code == 200


async def test_create_agency_forbidden_with_only_agency_list_scope(client, as_principal):
    as_principal(role="user", scopes=["agency:list"])
    r = await client.post("/api/v1/agencies", json={"name": "New", "short_name": "N"})
    assert r.status_code == 403


async def test_create_agency_allowed_with_agency_write_scope(client, as_principal):
    as_principal(role="user", scopes=["agency:write"])
    r = await client.post("/api/v1/agencies", json={"name": "New", "short_name": "N", "status": "draft"})
    assert r.status_code == 201
