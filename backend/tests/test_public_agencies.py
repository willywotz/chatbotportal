from app.features.agency.models.agency import AgencyStatus, ConnectionType
from app.features.agency.repositories import agency as agency_repo
from app.features.analytics.routers.public_status import public_agencies


async def test_public_agencies_display_fields_only(db_session):
    ag = await agency_repo.create(
        db_session,
        name="กรมการปกครอง",
        short_name="ปค.",
        logo="🏛️",
        description="บัตรประชาชน ทะเบียนบ้าน",
        connection_type=ConnectionType.MCP,
        status=AgencyStatus.active,
        endpoint_url="https://secret.internal/api",
    )

    rows = await public_agencies(db_session)

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


async def test_public_agencies_excludes_draft(db_session):
    await agency_repo.create(db_session, name="Draft", status=AgencyStatus.draft)
    await agency_repo.create(db_session, name="Live", status=AgencyStatus.active)

    rows = await public_agencies(db_session)

    assert [r["name"] for r in rows] == ["Live"]
