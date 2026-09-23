"""Admin CRUD API for LLM providers, routes, and known purposes.

Mirrors `app/routers/agencies/crud.py` for CRUD shape and `app/routers/
settings.py` for secret masking: `api_key` is never returned in the clear,
and an update whose `api_key` is missing/masked leaves the stored key
untouched. Every mutation records an audit entry and invalidates the
route-resolution cache in `app.features.llm.services` so the next chat call picks
up the change.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.dependencies import require_scope
from app.core.security.principal import Principal
from app.core.db import get_db
from app.features.llm.models.llm_provider import LlmProvider
from app.features.llm.models.llm_route import LlmRoute
from app.features.settings.routers.settings import MASK
from app.features.llm.schemas.llm_provider import (
    LLMProviderCreate,
    LLMProviderListResponse,
    LLMProviderResponse,
    LLMProviderUpdate,
)
from app.features.llm.schemas.llm_route import (
    LLMRouteCreate,
    LLMRouteListResponse,
    LLMRouteResponse,
    LLMRouteTestResult,
    LLMRouteUpdate,
)
from app.core.audit import record_audit
from app.features.llm.services import KNOWN_PURPOSES, invalidate, ping
from app.features.llm.services import admin as llm_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/language-model", tags=["Language Model Admin"])


def _provider_response(provider: LlmProvider) -> LLMProviderResponse:
    return LLMProviderResponse(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        api_key=MASK,
        auth_header=provider.auth_header,
        auth_scheme=provider.auth_scheme,
        timeout_seconds=provider.timeout_seconds,
        request_usage=provider.request_usage,
        rate_limit_rps=provider.rate_limit_rps,
        rate_limit_rpm=provider.rate_limit_rpm,
        max_queue_size=provider.max_queue_size,
        enabled=provider.enabled,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


async def _route_response(session: AsyncSession, route: LlmRoute) -> LLMRouteResponse:
    provider_name = await llm_admin.route_provider_name(session, route)
    return LLMRouteResponse(
        id=route.id,
        purpose=route.purpose,
        provider_id=route.provider_id,
        provider_name=provider_name,
        model=route.model,
        timeout_override=route.timeout_override,
        enabled=route.enabled,
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


@router.get("/purposes", dependencies=[Security(require_scope, scopes=["llm:read"])], summary="List known LLM purposes")
async def list_purposes():
    return {"data": list(KNOWN_PURPOSES)}


@router.get(
    "/providers",
    response_model=LLMProviderListResponse,
    dependencies=[Security(require_scope, scopes=["llm:read"])],
    summary="List LLM providers",
)
async def list_providers(session: AsyncSession = Depends(get_db)):
    providers = await llm_admin.list_providers(session)
    return LLMProviderListResponse(data=[_provider_response(p) for p in providers], total=len(providers))


@router.post(
    "/providers",
    response_model=LLMProviderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create LLM provider",
)
async def create_provider(
    body: LLMProviderCreate,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["llm:write"]),
):
    provider = await llm_admin.create_provider(session, body.model_dump())
    await record_audit(session, user, "llm_provider.create", object_type="llm_provider", object_id=provider.id)
    invalidate()
    return _provider_response(provider)


@router.get(
    "/providers/{provider_id}",
    response_model=LLMProviderResponse,
    dependencies=[Security(require_scope, scopes=["llm:read"])],
    summary="Get LLM provider by ID",
)
async def get_provider(provider_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    provider = await llm_admin.get_provider(session, provider_id)
    return _provider_response(provider)


@router.patch(
    "/providers/{provider_id}",
    response_model=LLMProviderResponse,
    summary="Partial update LLM provider",
)
async def update_provider(
    provider_id: uuid.UUID,
    body: LLMProviderUpdate,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["llm:write"]),
):
    update_data = body.model_dump(exclude_unset=True)
    if update_data.get("api_key") in (None, MASK):
        update_data.pop("api_key", None)

    provider = await llm_admin.update_provider(session, provider_id, update_data)
    await record_audit(session, user, "llm_provider.update", object_type="llm_provider", object_id=provider.id)
    invalidate()
    return _provider_response(provider)


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete LLM provider",
)
async def delete_provider(
    provider_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["llm:write"]),
):
    await llm_admin.delete_provider(session, provider_id)
    await record_audit(session, user, "llm_provider.delete", object_type="llm_provider", object_id=provider_id)
    invalidate()


@router.get(
    "/routes",
    response_model=LLMRouteListResponse,
    dependencies=[Security(require_scope, scopes=["llm:read"])],
    summary="List LLM routes",
)
async def list_routes(session: AsyncSession = Depends(get_db)):
    routes = await llm_admin.list_routes(session)
    data = [await _route_response(session, r) for r in routes]
    return LLMRouteListResponse(data=data, total=len(data))


@router.post(
    "/routes",
    response_model=LLMRouteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create LLM route",
)
async def create_route(
    body: LLMRouteCreate,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["llm:write"]),
):
    route = await llm_admin.create_route(session, body.model_dump())
    await record_audit(session, user, "llm_route.create", object_type="llm_route", object_id=route.id)
    invalidate()
    return await _route_response(session, route)


@router.post(
    "/routes/{purpose}/test",
    response_model=LLMRouteTestResult,
    dependencies=[Security(require_scope, scopes=["llm:write"])],
    summary="Test an LLM route end-to-end",
)
async def test_route(purpose: str, session: AsyncSession = Depends(get_db)):
    if purpose not in KNOWN_PURPOSES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown purpose")
    result = await ping(session, purpose)
    return LLMRouteTestResult(ok=result.ok, latency_ms=result.latency_ms,
                              model=result.model, error=result.error)


@router.get(
    "/routes/{route_id}",
    response_model=LLMRouteResponse,
    dependencies=[Security(require_scope, scopes=["llm:read"])],
    summary="Get LLM route by ID",
)
async def get_route(route_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    route = await llm_admin.get_route(session, route_id)
    return await _route_response(session, route)


@router.patch(
    "/routes/{route_id}",
    response_model=LLMRouteResponse,
    summary="Partial update LLM route",
)
async def update_route(
    route_id: uuid.UUID,
    body: LLMRouteUpdate,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["llm:write"]),
):
    update_data = body.model_dump(exclude_unset=True)
    route = await llm_admin.update_route(session, route_id, update_data)
    await record_audit(session, user, "llm_route.update", object_type="llm_route", object_id=route.id)
    invalidate()
    return await _route_response(session, route)


@router.delete(
    "/routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete LLM route",
)
async def delete_route(
    route_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["llm:write"]),
):
    await llm_admin.delete_route(session, route_id)
    await record_audit(session, user, "llm_route.delete", object_type="llm_route", object_id=route_id)
    invalidate()
