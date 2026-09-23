from app.features.agency.schemas.agency import (
    AgencyCreate,
    AgencyHealthEmbed,
    HealthHistoryBucket,
    McpDiscoverRequest,
    StatusUpdateRequest,
)


def test_agency_create_accepts_routing_fields():
    body = AgencyCreate(
        name="x", priority=2, router_hint="ภาษี",
        dispatch_timeout_s=30, mcp_tool_name="chat",
    )
    assert body.priority == 2
    assert body.router_hint == "ภาษี"
    assert body.dispatch_timeout_s == 30
    assert body.mcp_tool_name == "chat"


def test_health_embed_shape():
    h = AgencyHealthEmbed(state="up", uptime_24h=99.2, avg_latency_ms_24h=320, last_check_at=None)
    assert h.state == "up"


def test_status_update_and_discover_request():
    assert StatusUpdateRequest(status="active").status == "active"
    assert McpDiscoverRequest(endpoint_url="https://x").endpoint_url == "https://x"


def test_history_bucket_fields():
    from datetime import datetime, timezone
    b = HealthHistoryBucket(bucket_start=datetime(2026, 6, 11, tzinfo=timezone.utc), uptime_pct=99.0, avg_latency_ms=300, checks=12, failures=0)
    assert b.checks == 12
