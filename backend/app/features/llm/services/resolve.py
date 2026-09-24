import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services.errors import LlmError

_CACHE_TTL_S = 30.0


@dataclass(frozen=True)
class ResolvedRoute:
    provider_name: str
    kind: str
    model: str
    base_url: str | None
    api_key: str
    timeout: float
    max_retries: int
    rate_limit_rps: int | None
    rate_limit_rpm: int | None
    max_queue_size: int
    headers: dict[str, str]


_cache: dict[str, tuple[ResolvedRoute, float]] = {}


def invalidate() -> None:
    _cache.clear()


async def for_purpose(session: AsyncSession, purpose: str) -> ResolvedRoute:
    entry = _cache.get(purpose)
    if entry is not None and time.monotonic() - entry[1] < _CACHE_TTL_S:
        return entry[0]
    binding = await llm_repo.enabled_binding_for_purpose(session, purpose)
    if binding is None:
        raise LlmError(f"no enabled binding for purpose {purpose!r}", kind="config")
    provider = await llm_repo.get_provider(session, binding.provider_id)
    if provider is None or not provider.enabled:
        raise LlmError("provider missing or disabled", kind="config",
                       provider=getattr(provider, "name", None))
    resolved = ResolvedRoute(
        provider_name=provider.name, kind=provider.provider,
        model=binding.model_override or provider.model,
        base_url=provider.base_url, api_key=provider.api_key,
        timeout=binding.timeout_override or provider.timeout_seconds,
        max_retries=provider.max_retries,
        rate_limit_rps=provider.rate_limit_rps, rate_limit_rpm=provider.rate_limit_rpm,
        max_queue_size=provider.max_queue_size,
        headers={h["name"]: h["value"] for h in (provider.headers or []) if h.get("name")},
    )
    _cache[purpose] = (resolved, time.monotonic())
    return resolved
