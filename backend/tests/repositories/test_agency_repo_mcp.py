import pytest

from app.repositories import agency as agency_repo

pytestmark = pytest.mark.asyncio


async def test_list_for_mcp_returns_expected_keys(db_session):
    await agency_repo.create(
        db_session, name="A", short_name="A", status="active", connection_type="API",
        description="d", data_scope=["x"], endpoint_url="http://e", expected_payload={"q": "1"},
        api_headers=[{"name": "Authorization", "value": "s"}],
    )
    await db_session.flush()

    rows = await agency_repo.list_for_mcp(db_session)

    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {
        "id", "name", "status", "description", "connection_type",
        "data_scope", "endpoint_url", "expected_payload", "api_headers",
    }
    assert row["name"] == "A"
    assert row["connection_type"] == "API"
    assert row["expected_payload"] == {"q": "1"}
    assert row["api_headers"] == [{"name": "Authorization", "value": "s"}]
