"""Agency logo upload/serve/delete — HTTP-level tests against a tmp UPLOAD_DIR.

Mirrors tests/routers/test_popular_questions_router.py: `db` fixture (in-memory
SQLite) + httpx AsyncClient over the real ASGI app, auth via
`dependency_overrides[get_current_user]`.
"""
import hashlib
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.security import generate_api_key, hash_api_key
from app.config import settings
from app.main import app
from app.models import Agency
from app.models.user import User, UserAPIKey

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 32
_WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32


def _admin():
    return User(id=uuid.uuid4(), email="admin@x.io", role="admin")


def _plain_user():
    return User(id=uuid.uuid4(), email="user@x.io", role="user")


async def _client(user=None):
    if user is not None:
        app.dependency_overrides[get_current_user] = user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.fixture(autouse=True)
def _tmp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    yield tmp_path


def _logos_dir(tmp_path: Path) -> Path:
    return tmp_path / "agency-logos"


@pytest.mark.usefixtures("db")
async def test_upload_valid_png_sets_logo_url_and_writes_file(_tmp_upload_dir):
    ag = await Agency.create(name="A", status="draft")
    async with await _client(_admin) as c:
        r = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.png", _PNG_BYTES, "image/png")},
        )
    app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    digest = hashlib.sha256(_PNG_BYTES).hexdigest()[:8]
    assert body["logo"] == f"/api/v1/agencies/{ag.id}/logo?v={digest}"

    refreshed = await Agency.get(id=ag.id)
    assert refreshed.logo == f"/api/v1/agencies/{ag.id}/logo?v={digest}"

    written = list(_logos_dir(_tmp_upload_dir).glob(f"{ag.id}-*"))
    assert len(written) == 1
    assert written[0].name == f"{ag.id}-{digest}.png"


@pytest.mark.usefixtures("db")
@pytest.mark.parametrize(
    "filename,content_type,data",
    [
        ("logo.jpg", "image/jpeg", _JPEG_BYTES),
        ("logo.webp", "image/webp", _WEBP_BYTES),
    ],
)
async def test_upload_accepts_jpeg_and_webp(filename, content_type, data):
    ag = await Agency.create(name="A", status="draft")
    async with await _client(_admin) as c:
        r = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": (filename, data, content_type)},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 200


@pytest.mark.usefixtures("db")
async def test_upload_rejects_non_image_content_type():
    ag = await Agency.create(name="A", status="draft")
    async with await _client(_admin) as c:
        r = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.txt", b"just plain text", "text/plain")},
        )
    app.dependency_overrides.clear()
    assert r.status_code in (400, 415)


@pytest.mark.usefixtures("db")
async def test_upload_rejects_bytes_that_dont_match_declared_type():
    """A fake extension/content-type whose bytes aren't a real image."""
    ag = await Agency.create(name="A", status="draft")
    async with await _client(_admin) as c:
        r = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.png", b"not actually a png", "image/png")},
        )
    app.dependency_overrides.clear()
    assert r.status_code in (400, 415)


@pytest.mark.usefixtures("db")
async def test_upload_rejects_oversized_file():
    ag = await Agency.create(name="A", status="draft")
    oversized = _PNG_BYTES + b"\x00" * (512 * 1024)
    async with await _client(_admin) as c:
        r = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.png", oversized, "image/png")},
        )
    app.dependency_overrides.clear()
    assert r.status_code in (400, 413)


@pytest.mark.usefixtures("db")
async def test_reupload_sweeps_orphaned_old_file(_tmp_upload_dir):
    ag = await Agency.create(name="A", status="draft")
    async with await _client(_admin) as c:
        r1 = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.png", _PNG_BYTES, "image/png")},
        )
        assert r1.status_code == 200
        old_digest = hashlib.sha256(_PNG_BYTES).hexdigest()[:8]

        new_bytes = _PNG_BYTES + b"\x01"
        r2 = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.png", new_bytes, "image/png")},
        )
    app.dependency_overrides.clear()

    assert r2.status_code == 200
    new_digest = hashlib.sha256(new_bytes).hexdigest()[:8]
    assert new_digest != old_digest
    assert r2.json()["logo"] == f"/api/v1/agencies/{ag.id}/logo?v={new_digest}"

    remaining = sorted(p.name for p in _logos_dir(_tmp_upload_dir).glob(f"{ag.id}-*"))
    assert remaining == [f"{ag.id}-{new_digest}.png"]


@pytest.mark.usefixtures("db")
async def test_upload_forbidden_for_non_owner_non_admin():
    ag = await Agency.create(name="A", status="draft")
    async with await _client(_plain_user) as c:
        r = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.png", _PNG_BYTES, "image/png")},
        )
    app.dependency_overrides.clear()
    assert r.status_code == 403


@pytest.mark.usefixtures("db")
async def test_get_logo_returns_bytes_with_cache_headers():
    ag = await Agency.create(name="A", status="draft")
    async with await _client(_admin) as c:
        upload = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.png", _PNG_BYTES, "image/png")},
        )
        assert upload.status_code == 200
        logo_url = upload.json()["logo"]
        r = await c.get(logo_url)
    app.dependency_overrides.clear()

    assert r.status_code == 200
    assert r.content == _PNG_BYTES
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-type"] == "image/png"


@pytest.mark.usefixtures("db")
async def test_get_logo_404_for_emoji_only_agency():
    ag = await Agency.create(name="A", status="draft", logo="🏛️")
    async with await _client() as c:
        r = await c.get(f"/api/v1/agencies/{ag.id}/logo")
    assert r.status_code == 404


@pytest.mark.usefixtures("db")
@pytest.mark.parametrize("role", ["user", "viewer", "auditor"])
async def test_get_logo_allowed_for_authenticated_read_only_roles(role):
    """Regression: the role allowlist chokepoint must not 403 an <img> fetch
    carrying an API key for a role that isn't otherwise allowlisted for this path."""
    ag = await Agency.create(name="A", status="draft")
    async with await _client(_admin) as c:
        upload = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.png", _PNG_BYTES, "image/png")},
        )
    app.dependency_overrides.clear()
    logo_url = upload.json()["logo"]

    user = await User.create(email=f"logo-{role}@x.io", hashed_password="h", role=role)
    raw = generate_api_key()
    await UserAPIKey.create(user_id=user.id, name="n", key_hash=hash_api_key(raw), key_prefix=raw[:12])
    async with await _client() as c:
        r = await c.get(logo_url, headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200


@pytest.mark.usefixtures("db")
async def test_delete_agency_removes_logo_file(_tmp_upload_dir):
    ag = await Agency.create(name="A", status="draft")
    async with await _client(_admin) as c:
        upload = await c.post(
            f"/api/v1/agencies/{ag.id}/logo",
            files={"file": ("logo.png", _PNG_BYTES, "image/png")},
        )
        assert upload.status_code == 200
        delete = await c.delete(f"/api/v1/agencies/{ag.id}")
    app.dependency_overrides.clear()

    assert delete.status_code == 204
    assert list(_logos_dir(_tmp_upload_dir).glob(f"{ag.id}-*")) == []
