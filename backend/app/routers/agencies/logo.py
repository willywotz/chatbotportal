"""Agency logo image upload/serve.

Filesystem storage under {UPLOAD_DIR}/agency-logos/ (see app.config.settings).
See docs/adr/0003-agency-logo-image-upload.md for the design.
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.auth.dependencies import require_admin
from app.config import settings
from app.models.user import User
from app.routers.agencies._utils import _with_health
from app.schemas.agency import AgencyResponse
from app.services import agency as agency_service

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_LOGO_BYTES = 512 * 1024

_NOSNIFF_CACHE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "public, max-age=31536000, immutable",
}

# content-type -> (extension, magic-byte validator). SVG is deliberately
# excluded (XSS surface via inline <script>).
_MAGIC_VALIDATORS: dict[str, tuple[str, Callable[[bytes], bool]]] = {
    "image/png": ("png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/jpeg": ("jpg", lambda b: b.startswith(b"\xff\xd8\xff")),
    "image/webp": ("webp", lambda b: b.startswith(b"RIFF") and b[8:12] == b"WEBP"),
}
_MEDIA_TYPE_FOR_EXT = {ext: content_type for content_type, (ext, _) in _MAGIC_VALIDATORS.items()}


def _logos_dir() -> Path:
    path = Path(settings.UPLOAD_DIR) / "agency-logos"
    path.mkdir(parents=True, mode=0o755, exist_ok=True)
    return path


def sweep_agency_logo_files(agency_id: uuid.UUID | str) -> None:
    """Best-effort delete of any existing {agency_id}-* logo file(s)."""
    try:
        for existing in _logos_dir().glob(f"{agency_id}-*"):
            existing.unlink(missing_ok=True)
    except OSError:
        logger.exception("failed to sweep logo files for agency %s", agency_id)


@router.post("/{agency_id}/logo", response_model=AgencyResponse, summary="Upload agency logo image")
async def upload_agency_logo(
    agency_id: uuid.UUID,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
):
    agency = await agency_service.get_agency_or_404(agency_id)

    validator = _MAGIC_VALIDATORS.get(file.content_type)
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image type; must be PNG, JPEG, or WebP",
        )
    ext, magic_matches = validator

    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Logo file exceeds 512KB")
    if not magic_matches(data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match declared image type",
        )

    sweep_agency_logo_files(agency_id)

    digest = hashlib.sha256(data).hexdigest()[:8]
    path = _logos_dir() / f"{agency_id}-{digest}.{ext}"
    path.write_bytes(data)
    path.chmod(0o644)

    agency = await agency_service.update_logo(agency, f"/api/v1/agencies/{agency_id}/logo?v={digest}")
    return await _with_health(agency)


@router.get("/{agency_id}/logo", summary="Get agency logo image")
async def get_agency_logo(agency_id: uuid.UUID):
    matches = sorted(_logos_dir().glob(f"{agency_id}-*"))
    if not matches:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo not found")
    path = matches[0]
    media_type = _MEDIA_TYPE_FOR_EXT.get(path.suffix.lstrip("."), "application/octet-stream")
    return FileResponse(path, media_type=media_type, headers=_NOSNIFF_CACHE_HEADERS)
