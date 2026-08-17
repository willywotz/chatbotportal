"""Admin CRUD data access for LLM providers and routes.

Kept separate from `app.routers.llm` so the router only orchestrates: parse
input, call this service, map to a schema, return. Mirrors `app.services.user`
in raising `HTTPException` directly for not-found/conflict cases.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from tortoise.exceptions import DoesNotExist

from app.models import LlmProvider, LlmRoute


async def list_providers() -> list[LlmProvider]:
    return await LlmProvider.all()


async def create_provider(data: dict) -> LlmProvider:
    return await LlmProvider.create(**data)


async def get_provider(provider_id: uuid.UUID) -> LlmProvider:
    try:
        return await LlmProvider.get(id=provider_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")


async def update_provider(provider_id: uuid.UUID, update_data: dict) -> LlmProvider:
    provider = await get_provider(provider_id)
    await provider.update_from_dict(update_data).save()
    return provider


async def delete_provider(provider_id: uuid.UUID) -> None:
    provider = await get_provider(provider_id)
    if await LlmRoute.filter(provider_id=provider_id).exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="provider in use by routes")
    await provider.delete()


async def list_routes() -> list[LlmRoute]:
    return await LlmRoute.all()


async def route_provider_name(route: LlmRoute) -> str:
    provider = await route.provider  # lazy FK load
    return provider.name


async def create_route(data: dict) -> LlmRoute:
    if not await LlmProvider.filter(id=data["provider_id"]).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    if await LlmRoute.filter(purpose=data["purpose"]).exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="route for purpose already exists")
    return await LlmRoute.create(**data)


async def get_route(route_id: uuid.UUID) -> LlmRoute:
    try:
        return await LlmRoute.get(id=route_id)
    except DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")


async def update_route(route_id: uuid.UUID, update_data: dict) -> LlmRoute:
    route = await get_route(route_id)

    if update_data.get("provider_id") is not None:
        if not await LlmProvider.filter(id=update_data["provider_id"]).exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    if update_data.get("purpose") is not None:
        if await LlmRoute.filter(purpose=update_data["purpose"]).exclude(id=route_id).exists():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="route for purpose already exists")

    await route.update_from_dict(update_data).save()
    return route


async def delete_route(route_id: uuid.UUID) -> None:
    route = await get_route(route_id)
    await route.delete()
