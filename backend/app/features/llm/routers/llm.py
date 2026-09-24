"""Admin CRUD API for LLM providers, bindings, kinds, and purposes.

`api_key` is never returned in the clear, and an update whose `api_key` is
missing or masked leaves the stored key untouched. Every mutation records an
audit entry and invalidates the resolution cache in
`app.features.llm.services` so the next chat call picks up the change.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.db import get_db
from app.core.security.dependencies import require_scope
from app.core.security.principal import Principal
from app.features.llm.models.llm_binding import LlmBinding
from app.features.llm.models.llm_provider import LlmProvider
from app.features.llm.schemas.llm_binding import (
    LLMBindingCreate,
    LLMBindingListResponse,
    LLMBindingResponse,
    LLMBindingTestResult,
    LLMBindingUpdate,
)
from app.features.llm.schemas.llm_provider import (
    LLMProviderCreate,
    LLMProviderListResponse,
    LLMProviderResponse,
    LLMProviderUpdate,
)
from app.features.llm.services import KNOWN_PURPOSES, invalidate, known_kinds, ping
from app.features.llm.services import admin as llm_admin
from app.features.settings.routers.settings import MASK

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/language-model", tags=["Language Model Admin"])


def _provider_response(provider: LlmProvider) -> LLMProviderResponse:
    return LLMProviderResponse(
        id=provider.id,
        name=provider.name,
        provider=provider.provider,
        model=provider.model,
        base_url=provider.base_url,
        api_key=MASK,
        timeout_seconds=provider.timeout_seconds,
        max_retries=provider.max_retries,
        rate_limit_rps=provider.rate_limit_rps,
        rate_limit_rpm=provider.rate_limit_rpm,
        max_queue_size=provider.max_queue_size,
        enabled=provider.enabled,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


async def _binding_response(session: AsyncSession, binding: LlmBinding) -> LLMBindingResponse:
    provider = await llm_admin.binding_provider(session, binding)
    return LLMBindingResponse(
        id=binding.id,
        purpose=binding.purpose,
        provider_id=binding.provider_id,
        provider_name=provider.name,
        model=binding.model_override or provider.model,
        fallback_binding_id=binding.fallback_binding_id,
        timeout_override=binding.timeout_override,
        enabled=binding.enabled,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


@router.get("/kinds", dependencies=[Security(require_scope, scopes=["llm:read"])], summary="List known provider kinds")
async def list_kinds():
    return {"data": list(known_kinds())}


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
    "/bindings",
    response_model=LLMBindingListResponse,
    dependencies=[Security(require_scope, scopes=["llm:read"])],
    summary="List LLM bindings",
)
async def list_bindings(session: AsyncSession = Depends(get_db)):
    bindings = await llm_admin.list_bindings(session)
    data = [await _binding_response(session, b) for b in bindings]
    return LLMBindingListResponse(data=data, total=len(data))


@router.post(
    "/bindings",
    response_model=LLMBindingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create LLM binding",
)
async def create_binding(
    body: LLMBindingCreate,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["llm:write"]),
):
    binding = await llm_admin.create_binding(session, body.model_dump())
    await record_audit(session, user, "llm_binding.create", object_type="llm_binding", object_id=binding.id)
    invalidate()
    return await _binding_response(session, binding)


@router.post(
    "/bindings/{purpose}/test",
    response_model=LLMBindingTestResult,
    dependencies=[Security(require_scope, scopes=["llm:write"])],
    summary="Test an LLM binding end-to-end",
)
async def test_binding(purpose: str, session: AsyncSession = Depends(get_db)):
    if purpose not in KNOWN_PURPOSES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown purpose")
    result = await ping(session, purpose)
    return LLMBindingTestResult(ok=result.ok, latency_ms=result.latency_ms,
                                model=result.model, error=result.error)


@router.get(
    "/bindings/{binding_id}",
    response_model=LLMBindingResponse,
    dependencies=[Security(require_scope, scopes=["llm:read"])],
    summary="Get LLM binding by ID",
)
async def get_binding(binding_id: uuid.UUID, session: AsyncSession = Depends(get_db)):
    binding = await llm_admin.get_binding(session, binding_id)
    return await _binding_response(session, binding)


@router.patch(
    "/bindings/{binding_id}",
    response_model=LLMBindingResponse,
    summary="Partial update LLM binding",
)
async def update_binding(
    binding_id: uuid.UUID,
    body: LLMBindingUpdate,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["llm:write"]),
):
    update_data = body.model_dump(exclude_unset=True)
    binding = await llm_admin.update_binding(session, binding_id, update_data)
    await record_audit(session, user, "llm_binding.update", object_type="llm_binding", object_id=binding.id)
    invalidate()
    return await _binding_response(session, binding)


@router.delete(
    "/bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete LLM binding",
)
async def delete_binding(
    binding_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: Principal = Security(require_scope, scopes=["llm:write"]),
):
    await llm_admin.delete_binding(session, binding_id)
    await record_audit(session, user, "llm_binding.delete", object_type="llm_binding", object_id=binding_id)
    invalidate()
