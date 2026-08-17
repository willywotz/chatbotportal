from app.models import Agency
from app.routers.public_status import public_agencies


async def test_public_agencies_display_fields_only(db):
    ag = await Agency.create(
        name="กรมการปกครอง",
        short_name="ปค.",
        logo="🏛️",
        description="บัตรประชาชน ทะเบียนบ้าน",
        connection_type="MCP",
        status="active",
        endpoint_url="https://secret.internal/api",
    )

    rows = await public_agencies()

    assert rows == [
        {
            "id": str(ag.id),
            "name": "กรมการปกครอง",
            "short_name": "ปค.",
            "logo": "🏛️",
            "description": "บัตรประชาชน ทะเบียนบ้าน",
            "connection_type": "MCP",
            "status": "active",
        }
    ]
    assert "endpoint_url" not in rows[0]


async def test_public_agencies_excludes_draft(db):
    await Agency.create(name="Draft", status="draft")
    await Agency.create(name="Live", status="active")

    rows = await public_agencies()

    assert [r["name"] for r in rows] == ["Live"]
