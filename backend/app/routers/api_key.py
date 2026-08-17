from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.user import User, UserAPIKey
from app.services import api_key as api_key_service
from app.services.audit import record_audit
from app.utils import now

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    last_used_at: str | None
    created_at: str
    expires_at: str | None
    revoked_at: str | None
    status: str


class CreatedAPIKeyResponse(APIKeyResponse):
    key: str  # full key — shown only in the create response


class CreateAPIKeyRequest(BaseModel):
    name: str
    expires_in_days: int | None = None


class UpdateAPIKeyRequest(BaseModel):
    name: str


def _status(k: UserAPIKey) -> str:
    if k.revoked_at is not None:
        return "revoked"
    if k.expires_at is not None and k.expires_at <= now():
        return "expired"
    return "active"


def _resp(k: UserAPIKey) -> APIKeyResponse:
    return APIKeyResponse(
        id=str(k.id),
        name=k.name,
        key_prefix=k.key_prefix,
        last_used_at=str(k.last_used_at) if k.last_used_at else None,
        created_at=str(k.created_at),
        expires_at=str(k.expires_at) if k.expires_at else None,
        revoked_at=str(k.revoked_at) if k.revoked_at else None,
        status=_status(k),
    )


@router.get("/", summary="List API keys for the current user")
async def list_api_keys(user: User = Depends(get_current_user)) -> list[APIKeyResponse]:
    result = await api_key_service.list_for_user(user.id)
    return [_resp(k) for k in result]


@router.post("/", summary="Create a new API key")
async def create_api_key(body: CreateAPIKeyRequest, user: User = Depends(get_current_user)) -> CreatedAPIKeyResponse:
    new_key, raw = await api_key_service.create(user.id, body.name, body.expires_in_days)
    return CreatedAPIKeyResponse(**_resp(new_key).model_dump(), key=raw)


@router.patch("/{key_id}", summary="Rename an API key")
async def update_api_key(key_id: str, body: UpdateAPIKeyRequest, user: User = Depends(get_current_user)) -> APIKeyResponse:
    key = await api_key_service.rename(key_id, user.id, body.name)
    return _resp(key)


@router.delete("/{key_id}", summary="Delete an API key")
async def delete_api_key(key_id: str, user: User = Depends(get_current_user)) -> dict:
    await api_key_service.delete(key_id, user.id)
    return {"detail": "API key deleted"}


@router.post("/{key_id}/revoke", summary="Revoke an API key (keeps it for audit; stops it working)")
async def revoke_api_key(key_id: str, user: User = Depends(get_current_user)) -> APIKeyResponse:
    key = await api_key_service.revoke(key_id, user.id)
    await record_audit(user, "api_key.revoke", object_type="api_key", object_id=key_id)
    return _resp(key)
