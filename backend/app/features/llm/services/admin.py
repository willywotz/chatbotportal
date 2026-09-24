"""Admin CRUD data access for LLM providers and bindings.

Kept separate from `app.features.llm.routers.llm` so the router only
orchestrates: parse input, call this service, map to a schema, return.
Raises `ApiError` directly for not-found/conflict/validation cases.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode
from app.features.llm.models.llm_binding import LlmBinding
from app.features.llm.models.llm_provider import LlmProvider
from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services import providers as provider_registry

_MAX_FALLBACK_WALK = 5


async def list_providers(session: AsyncSession) -> list[LlmProvider]:
    return await llm_repo.list_providers(session)


async def create_provider(session: AsyncSession, data: dict) -> LlmProvider:
    kind = data.get("provider", "openai")
    if kind not in provider_registry.known_kinds():
        raise ApiError(ErrorCode.INVALID_REQUEST, f"unknown provider kind {kind!r}", status=422)
    return await llm_repo.create_provider(session, **data)


async def get_provider(session: AsyncSession, provider_id: uuid.UUID) -> LlmProvider:
    provider = await llm_repo.get_provider(session, provider_id)
    if provider is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Provider not found", status=404)
    return provider


async def update_provider(session: AsyncSession, provider_id: uuid.UUID, update_data: dict) -> LlmProvider:
    provider = await get_provider(session, provider_id)
    kind = update_data.get("provider")
    if kind is not None and kind not in provider_registry.known_kinds():
        raise ApiError(ErrorCode.INVALID_REQUEST, f"unknown provider kind {kind!r}", status=422)
    return await llm_repo.update_provider(session, provider, update_data)


async def delete_provider(session: AsyncSession, provider_id: uuid.UUID) -> None:
    provider = await get_provider(session, provider_id)
    if await llm_repo.provider_has_bindings(session, provider_id):
        raise ApiError(ErrorCode.CONFLICT, "provider in use by bindings", status=409)
    await llm_repo.delete_provider(session, provider)


async def list_bindings(session: AsyncSession) -> list[LlmBinding]:
    return await llm_repo.list_bindings(session)


async def binding_provider(session: AsyncSession, binding: LlmBinding) -> LlmProvider:
    return await llm_repo.get_provider(session, binding.provider_id)


async def validate_fallback(session: AsyncSession, binding_id, fallback_id) -> None:
    if fallback_id is None:
        return
    if fallback_id == binding_id:
        raise ApiError(ErrorCode.CONFLICT, "binding cannot fall back to itself", status=409)
    seen = {binding_id}
    node = fallback_id
    depth = 0
    while node is not None and depth < _MAX_FALLBACK_WALK:
        if node in seen:
            raise ApiError(ErrorCode.CONFLICT, "fallback chain forms a cycle", status=409)
        seen.add(node)
        b = await llm_repo.get_binding(session, node)
        node = b.fallback_binding_id if b else None
        depth += 1


async def create_binding(session: AsyncSession, data: dict) -> LlmBinding:
    if await llm_repo.get_provider(session, data["provider_id"]) is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Provider not found", status=404)
    if await llm_repo.binding_purpose_exists(session, data["purpose"]):
        raise ApiError(ErrorCode.CONFLICT, "binding for purpose already exists", status=409)
    await validate_fallback(session, None, data.get("fallback_binding_id"))
    return await llm_repo.create_binding(session, **data)


async def get_binding(session: AsyncSession, binding_id: uuid.UUID) -> LlmBinding:
    binding = await llm_repo.get_binding(session, binding_id)
    if binding is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Binding not found", status=404)
    return binding


async def update_binding(session: AsyncSession, binding_id: uuid.UUID, update_data: dict) -> LlmBinding:
    binding = await get_binding(session, binding_id)
    if update_data.get("provider_id") is not None:
        if await llm_repo.get_provider(session, update_data["provider_id"]) is None:
            raise ApiError(ErrorCode.NOT_FOUND, "Provider not found", status=404)
    if "fallback_binding_id" in update_data:
        await validate_fallback(session, binding_id, update_data["fallback_binding_id"])
    return await llm_repo.update_binding(session, binding, update_data)


async def delete_binding(session: AsyncSession, binding_id: uuid.UUID) -> None:
    binding = await get_binding(session, binding_id)
    await llm_repo.delete_binding(session, binding)
