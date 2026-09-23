"""Guards that agency logo image upload/serve endpoints stay removed.

The filesystem-backed logo upload feature and its {UPLOAD_DIR} storage were
removed; agency `logo` is now an emoji or an external URL set through ordinary
CRUD only. These endpoints must no longer exist.
"""
from app.features.agency.repositories import agency as agency_repo


async def test_upload_logo_endpoint_is_removed(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    r = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert r.status_code == 404


async def test_public_serve_logo_endpoint_is_removed(client, db_session):
    ag = await agency_repo.create(db_session, name="A", status="draft")
    r = await client.get(f"/api/v1/public/agencies/{ag.id}/logo")
    assert r.status_code == 404
