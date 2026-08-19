import json

from fastapi import APIRouter, Depends, Security
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_scope
from app.auth.keycloak import Principal
from app.config import (
    SETTINGS_GROUPS,
    SECRET_FIELD_NAMES,
    settings,
    load_settings_from_db,
)
from app.db import get_db
from app.schemas.settings import (
    SettingFieldOut,
    SettingsGroupOut,
    SettingsResponse,
    SettingsUpdateRequest,
)
from app.services import settings as settings_service
from app.services.audit import record_audit
from app.services.cache_flush import flush_similarity_cache

router = APIRouter(tags=["Settings"])

ALL_KEYS = {k for keys in SETTINGS_GROUPS.values() for k in keys}
MASK = "*****"


def _field_type_for(annotation: type) -> str:
    from typing import get_origin
    origin = get_origin(annotation)
    if annotation is bool:
        return "bool"
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    if origin is list or annotation in (list, list[str]):
        return "list_str"
    return "str"


def _serialize_current(key: str) -> str:
    val = getattr(settings, key)
    if isinstance(val, list):
        return json.dumps(val)
    return str(val)


def _serialize_default(key: str) -> str:
    field_info = settings.model_fields.get(key)
    if field_info is None:
        return ""
    val = field_info.default
    if isinstance(val, list):
        return json.dumps(val)
    if val is not None:
        return str(val)
    return ""


@router.get("/settings", response_model=SettingsResponse,
            dependencies=[Security(require_scope, scopes=["settings:read"])])
async def list_settings(session: AsyncSession = Depends(get_db)):
    db_map = await settings_service.fetch_db_settings(session)

    groups = []
    for group_name, keys in SETTINGS_GROUPS.items():
        fields = []
        for key in keys:
            field_info = settings.model_fields.get(key)
            if field_info is None:
                continue
            is_secret = key in SECRET_FIELD_NAMES
            current = _serialize_current(key)
            if key in db_map:
                display_val = MASK if is_secret else db_map[key].value
            else:
                display_val = MASK if is_secret else current
            fields.append(SettingFieldOut(
                key=key,
                value=display_val,
                field_type=_field_type_for(field_info.annotation),
                group=group_name,
                is_secret=is_secret,
                default_value=_serialize_default(key),
            ))
        groups.append(SettingsGroupOut(group=group_name, fields=fields))

    return SettingsResponse(groups=groups)


@router.put("/settings")
async def update_settings(
    body: SettingsUpdateRequest,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["settings:write"]),
):
    updated_keys: list[str] = []
    for item in body.settings:
        if item.key not in ALL_KEYS:
            continue
        if item.key in SECRET_FIELD_NAMES and item.value == MASK:
            continue
        await settings_service.upsert_setting(
            session, item.key, item.value, user.email, _group_for_key(item.key),
            _field_type_for(settings.model_fields[item.key].annotation),
        )
        updated_keys.append(item.key)
    await load_settings_from_db()
    await record_audit(session, user, "settings.update", object_type="settings", detail={"keys": updated_keys})
    return {"detail": "Settings updated"}


def _group_for_key(key: str) -> str:
    for group_name, keys in SETTINGS_GROUPS.items():
        if key in keys:
            return group_name
    return "App"


@router.post("/settings/cache/flush", dependencies=[Security(require_scope, scopes=["settings:write"])])
async def flush_cache(session: AsyncSession = Depends(get_db)):
    await flush_similarity_cache(session)
    return {"detail": "cache flushed"}
