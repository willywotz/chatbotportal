"""Agency logo upload/serve/delete — HTTP-level tests against a tmp UPLOAD_DIR.

httpx AsyncClient over the real ASGI app (the `client` fixture), auth via the
as_principal fixture, seeding via `db_session`. The logo GET lives under
/public, so it needs no auth.
"""
import hashlib
from pathlib import Path

import pytest

from app.config import settings
from app.models import Agency
from app.repositories import agency as agency_repo

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 32
_WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32

_USER_SCOPES = ["agency:list", "conversation:read:own", "conversation:write:own", "message:rate"]


@pytest.fixture(autouse=True)
def _tmp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    yield tmp_path


def _logos_dir(tmp_path: Path) -> Path:
    return tmp_path / "agency-logos"


async def test_upload_valid_png_sets_logo_url_and_writes_file(_tmp_upload_dir, client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    r = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )

    assert r.status_code == 200
    body = r.json()
    digest = hashlib.sha256(_PNG_BYTES).hexdigest()[:8]
    assert body["logo"] == f"/api/v1/public/agencies/{ag.id}/logo?v={digest}"

    refreshed = await db_session.get(Agency, ag.id)
    assert refreshed.logo == f"/api/v1/public/agencies/{ag.id}/logo?v={digest}"

    written = list(_logos_dir(_tmp_upload_dir).glob(f"{ag.id}-*"))
    assert len(written) == 1
    assert written[0].name == f"{ag.id}-{digest}.png"


@pytest.mark.parametrize(
    "filename,content_type,data",
    [
        ("logo.jpg", "image/jpeg", _JPEG_BYTES),
        ("logo.webp", "image/webp", _WEBP_BYTES),
    ],
)
async def test_upload_accepts_jpeg_and_webp(filename, content_type, data, client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    r = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": (filename, data, content_type)},
    )
    assert r.status_code == 200


async def test_upload_rejects_non_image_content_type(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    r = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.txt", b"just plain text", "text/plain")},
    )
    assert r.status_code in (400, 415)


async def test_upload_rejects_bytes_that_dont_match_declared_type(client, as_principal, db_session):
    """A fake extension/content-type whose bytes aren't a real image."""
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    r = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", b"not actually a png", "image/png")},
    )
    assert r.status_code in (400, 415)


async def test_upload_rejects_oversized_file(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    oversized = _PNG_BYTES + b"\x00" * (512 * 1024)
    r = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", oversized, "image/png")},
    )
    assert r.status_code in (400, 413)


async def test_reupload_sweeps_orphaned_old_file(_tmp_upload_dir, client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    r1 = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    assert r1.status_code == 200
    old_digest = hashlib.sha256(_PNG_BYTES).hexdigest()[:8]

    new_bytes = _PNG_BYTES + b"\x01"
    r2 = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", new_bytes, "image/png")},
    )

    assert r2.status_code == 200
    new_digest = hashlib.sha256(new_bytes).hexdigest()[:8]
    assert new_digest != old_digest
    assert r2.json()["logo"] == f"/api/v1/public/agencies/{ag.id}/logo?v={new_digest}"

    remaining = sorted(p.name for p in _logos_dir(_tmp_upload_dir).glob(f"{ag.id}-*"))
    assert remaining == [f"{ag.id}-{new_digest}.png"]


async def test_upload_forbidden_for_non_owner_non_admin(client, as_principal, db_session):
    as_principal(role="user", scopes=_USER_SCOPES)
    ag = await agency_repo.create(db_session, name="A", status="draft")
    r = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    assert r.status_code == 403


async def test_get_logo_returns_bytes_with_cache_headers(client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    upload = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 200
    r = await client.get(f"/api/v1/public/agencies/{ag.id}/logo")

    assert r.status_code == 200
    assert r.content == _PNG_BYTES
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-type"] == "image/png"


async def test_get_logo_404_for_emoji_only_agency(client, db_session):
    ag = await agency_repo.create(db_session, name="A", status="draft", logo="🏛️")
    r = await client.get(f"/api/v1/public/agencies/{ag.id}/logo")
    assert r.status_code == 404


async def test_get_logo_allowed_with_no_token(client, as_principal, db_session):
    """The logo GET now lives under /public: an anonymous <img> fetch must succeed."""
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    upload = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 200
    r = await client.get(f"/api/v1/public/agencies/{ag.id}/logo")
    assert r.status_code == 200


async def test_delete_agency_removes_logo_file(_tmp_upload_dir, client, as_principal, db_session):
    as_principal()
    ag = await agency_repo.create(db_session, name="A", status="draft")
    upload = await client.post(
        f"/api/v1/agencies/{ag.id}/logo",
        files={"file": ("logo.png", _PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 200
    delete = await client.delete(f"/api/v1/agencies/{ag.id}")

    assert delete.status_code == 204
    assert list(_logos_dir(_tmp_upload_dir).glob(f"{ag.id}-*")) == []
