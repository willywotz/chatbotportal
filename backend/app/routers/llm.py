"""Admin CRUD API for LLM providers, routes, and known purposes.

Mirrors `app/routers/agencies/crud.py` for CRUD shape and `app/routers/
settings.py` for secret masking: `api_key` is never returned in the clear,
and an update whose `api_key` is missing/masked leaves the stored key
untouched. Every mutation records an audit entry and invalidates the
route-resolution cache in `app.services.llm` so the next chat call picks
up the change.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from tortoise.exceptions import DoesNotExist

from app.auth.dependencies import require_admin
from app.models import LlmProvider, LlmRoute
from app.models.user import User
from app.routers.settings import MASK
from app.schemas.llm_provider import (
    LLMProviderCreate,
    LLMProviderListResponse,
    LLMProviderResponse,
    LLMProviderUpdate,
)
from app.schemas.llm_route import (
    LLMRouteCreate,
    LLMRouteListResponse,
    LLMRouteResponse,
    LLMRouteTestResult,
    LLMRouteUpdate,
)
from app.services.audit import record_audit
from app.services.llm import KNOWN_PURPOSES, invalidate, ping

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


async def _route_response(route: LlmRoute) -> LLMRouteResponse:
    provider = await route.provider
    return LLMRouteResponse(
        id=route.id,
        purpose=route.purpose,
        provider_id=route.provider_id,
        provider_name=provider.name,
        model=route.model,
        timeout_override=route.timeout_override,
        enabled=route.enabled,
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


# ---------------------------------------------------------------------------
# Purposes
# ---------------------------------------------------------------------------

@router.get("/purposes", dependencies=[Depends(require_admin)], summary="List known LLM purposes")
async def list_purposes():
    return {"data": list(KNOWN_PURPOSES)}


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

@router.get(
    "/providers",
    response_model=LLMProviderListResponse,
    dependencies=[Depends(require_admin)],
    summary="List LLM providers",
)
async def list_providers():
    providers = await LlmProvider.all()
    return LLMProviderListResponse(data=[_provider_response(p) for p in providers], total=len(providers))


@router.post(
    "/providers",
    response_model=LLMProviderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create LLM provider",
)
async def create_provider(body: LLMProviderCreate, user: User = Depends(require_admin)):
    provider = await LlmProvider.create(**body.model_dump())
    await record_audit(user, "llm_provider.create", object_type="llm_provider", object_id=provider.id)
    invalidate()
    return _provider_response(provider)


@router.get(
    "/providers/{provider_id}",
    response_model=LLMProviderResponse,
    dependencies=[Depends(require_admin)],
    summary="Get LLM provider by ID",
)
async def get_provider(provider_id: uuid.UUID):
    try:
        provider = await LlmProvider.get(id=provider_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return _provider_response(provider)


@router.patch(
    "/providers/{provider_id}",
    response_model=LLMProviderResponse,
    summary="Partial update LLM provider",
)
async def update_provider(provider_id: uuid.UUID, body: LLMProviderUpdate, user: User = Depends(require_admin)):
    try:
        provider = await LlmProvider.get(id=provider_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    update_data = body.model_dump(exclude_unset=True)
    if update_data.get("api_key") in (None, MASK):
        update_data.pop("api_key", None)

    await provider.update_from_dict(update_data).save()
    await record_audit(user, "llm_provider.update", object_type="llm_provider", object_id=provider.id)
    invalidate()
    return _provider_response(provider)


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete LLM provider",
)
async def delete_provider(provider_id: uuid.UUID, user: User = Depends(require_admin)):
    try:
        provider = await LlmProvider.get(id=provider_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    if await LlmRoute.filter(provider_id=provider_id).exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="provider in use by routes")

    await provider.delete()
    await record_audit(user, "llm_provider.delete", object_type="llm_provider", object_id=provider_id)
    invalidate()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "/routes",
    response_model=LLMRouteListResponse,
    dependencies=[Depends(require_admin)],
    summary="List LLM routes",
)
async def list_routes():
    routes = await LlmRoute.all()
    data = [await _route_response(r) for r in routes]
    return LLMRouteListResponse(data=data, total=len(data))


@router.post(
    "/routes",
    response_model=LLMRouteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create LLM route",
)
async def create_route(body: LLMRouteCreate, user: User = Depends(require_admin)):
    if not await LlmProvider.filter(id=body.provider_id).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    if await LlmRoute.filter(purpose=body.purpose).exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="route for purpose already exists")

    route = await LlmRoute.create(**body.model_dump())
    await record_audit(user, "llm_route.create", object_type="llm_route", object_id=route.id)
    invalidate()
    return await _route_response(route)


@router.post(
    "/routes/{purpose}/test",
    response_model=LLMRouteTestResult,
    dependencies=[Depends(require_admin)],
    summary="Test an LLM route end-to-end",
)
async def test_route(purpose: str):
    if purpose not in KNOWN_PURPOSES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown purpose")
    result = await ping(purpose)
    return LLMRouteTestResult(ok=result.ok, latency_ms=result.latency_ms,
                              model=result.model, error=result.error)


@router.get(
    "/routes/{route_id}",
    response_model=LLMRouteResponse,
    dependencies=[Depends(require_admin)],
    summary="Get LLM route by ID",
)
async def get_route(route_id: uuid.UUID):
    try:
        route = await LlmRoute.get(id=route_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    return await _route_response(route)


@router.patch(
    "/routes/{route_id}",
    response_model=LLMRouteResponse,
    summary="Partial update LLM route",
)
async def update_route(route_id: uuid.UUID, body: LLMRouteUpdate, user: User = Depends(require_admin)):
    try:
        route = await LlmRoute.get(id=route_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")

    update_data = body.model_dump(exclude_unset=True)

    if update_data.get("provider_id") is not None:
        if not await LlmProvider.filter(id=update_data["provider_id"]).exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    if update_data.get("purpose") is not None:
        if await LlmRoute.filter(purpose=update_data["purpose"]).exclude(id=route_id).exists():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="route for purpose already exists")

    await route.update_from_dict(update_data).save()
    await record_audit(user, "llm_route.update", object_type="llm_route", object_id=route.id)
    invalidate()
    return await _route_response(route)


@router.delete(
    "/routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete LLM route",
)
async def delete_route(route_id: uuid.UUID, user: User = Depends(require_admin)):
    try:
        route = await LlmRoute.get(id=route_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")

    await route.delete()
    await record_audit(user, "llm_route.delete", object_type="llm_route", object_id=route_id)
    invalidate()
