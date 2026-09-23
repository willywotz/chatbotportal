"""Admin CRUD data access for LLM providers and routes.

Kept separate from `app.routers.llm` so the router only orchestrates: parse
input, call this service, map to a schema, return. Mirrors `app.services.user`
in raising `ApiError` directly for not-found/conflict cases.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError, ErrorCode
from app.models import LlmProvider, LlmRoute
from app.repositories import llm as llm_repo


async def list_providers(session: AsyncSession) -> list[LlmProvider]:
    return await llm_repo.list_providers(session)


async def create_provider(session: AsyncSession, data: dict) -> LlmProvider:
    return await llm_repo.create_provider(session, **data)


async def get_provider(session: AsyncSession, provider_id: uuid.UUID) -> LlmProvider:
    provider = await llm_repo.get_provider(session, provider_id)
    if provider is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Provider not found", status=404)
    return provider


async def update_provider(session: AsyncSession, provider_id: uuid.UUID, update_data: dict) -> LlmProvider:
    provider = await get_provider(session, provider_id)
    return await llm_repo.update_provider(session, provider, update_data)


async def delete_provider(session: AsyncSession, provider_id: uuid.UUID) -> None:
    provider = await get_provider(session, provider_id)
    if await llm_repo.provider_has_routes(session, provider_id):
        raise ApiError(ErrorCode.CONFLICT, "provider in use by routes", status=409)
    await llm_repo.delete_provider(session, provider)


async def list_routes(session: AsyncSession) -> list[LlmRoute]:
    return await llm_repo.list_routes(session)


async def route_provider_name(session: AsyncSession, route: LlmRoute) -> str:
    provider = await llm_repo.get_provider(session, route.provider_id)
    return provider.name


async def create_route(session: AsyncSession, data: dict) -> LlmRoute:
    if await llm_repo.get_provider(session, data["provider_id"]) is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Provider not found", status=404)
    if await llm_repo.route_purpose_exists(session, data["purpose"]):
        raise ApiError(ErrorCode.CONFLICT, "route for purpose already exists", status=409)
    return await llm_repo.create_route(session, **data)


async def get_route(session: AsyncSession, route_id: uuid.UUID) -> LlmRoute:
    route = await llm_repo.get_route(session, route_id)
    if route is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Route not found", status=404)
    return route


async def update_route(session: AsyncSession, route_id: uuid.UUID, update_data: dict) -> LlmRoute:
    route = await get_route(session, route_id)

    if update_data.get("provider_id") is not None:
        if await llm_repo.get_provider(session, update_data["provider_id"]) is None:
            raise ApiError(ErrorCode.NOT_FOUND, "Provider not found", status=404)

    if update_data.get("purpose") is not None:
        if await llm_repo.route_purpose_exists(session, update_data["purpose"], exclude_id=route_id):
            raise ApiError(ErrorCode.CONFLICT, "route for purpose already exists", status=409)

    return await llm_repo.update_route(session, route, update_data)


async def delete_route(session: AsyncSession, route_id: uuid.UUID) -> None:
    route = await get_route(session, route_id)
    await llm_repo.delete_route(session, route)
