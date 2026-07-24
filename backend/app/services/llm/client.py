import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass

import httpx

from app.services.llm.purpose import KNOWN_PURPOSES, Purpose
from app.services.rate_limit import build_limiter

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 30.0


@dataclass
class LlmUsageInfo:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None


@dataclass
class LlmResult:
    content: str
    tool_calls: list | None
    usage: LlmUsageInfo
    raw: dict


class LlmError(Exception):
    def __init__(self, message: str, *, status: int | None = None,
                 provider: str | None = None, kind: str | None = None):
        super().__init__(message)
        self.status = status
        self.provider = provider
        self.kind = kind


@dataclass
class _Resolved:
    provider_name: str
    base_url: str
    api_key: str
    auth_header: str
    auth_scheme: str
    timeout: float
    request_usage: bool
    rate_limit_rps: int | None
    rate_limit_rpm: int | None
    max_queue_size: int
    model: str


_cache: dict[str, tuple[_Resolved, float]] = {}


def invalidate() -> None:
    _cache.clear()


async def _resolve(purpose: str) -> _Resolved:
    entry = _cache.get(purpose)
    if entry is not None and time.monotonic() - entry[1] < _CACHE_TTL_S:
        return entry[0]
    from app.models import LlmRoute
    route = await LlmRoute.filter(purpose=purpose, enabled=True).first()
    if route is None:
        raise LlmError(f"no enabled route for purpose {purpose!r}", kind="config")
    provider = await route.provider  # lazy FK load
    if not provider.enabled:
        raise LlmError(f"provider {provider.name!r} is disabled", provider=provider.name, kind="config")
    resolved = _Resolved(
        provider_name=provider.name, base_url=provider.base_url, api_key=provider.api_key,
        auth_header=provider.auth_header, auth_scheme=provider.auth_scheme,
        timeout=route.timeout_override if route.timeout_override is not None else provider.timeout_seconds,
        request_usage=provider.request_usage, rate_limit_rps=provider.rate_limit_rps,
        rate_limit_rpm=provider.rate_limit_rpm, max_queue_size=provider.max_queue_size,
        model=route.model,
    )
    _cache[purpose] = (resolved, time.monotonic())
    return resolved


_provider_limiter = build_limiter()
_queue_waiters: dict[str, int] = defaultdict(int)


async def _acquire(name: str, rps: int | None, rpm: int | None, max_queue_size: int) -> None:
    """Wait for a rate slot (rps then rpm windows). Fail fast when the queue is full.

    rps is acquired before rpm so a denied rpm wastes at most one rps slot (recovers
    within 1s); this never over-admits either window.
    """
    if not rps and not rpm:
        return
    if _queue_waiters[name] >= max_queue_size:
        raise LlmError(f"provider {name!r} rate-limit queue is full", provider=name, kind="queue_full")
    _queue_waiters[name] += 1
    try:
        while True:
            if rps:
                r = await _provider_limiter.check(f"llm:{name}:s", limit=rps, window_s=1.0)
                if not r.allowed:
                    await asyncio.sleep(max(r.retry_after, 0.02))
                    continue
            if rpm:
                r = await _provider_limiter.check(f"llm:{name}:m", limit=rpm, window_s=60.0)
                if not r.allowed:
                    await asyncio.sleep(max(r.retry_after, 0.02))
                    continue
            return
    finally:
        _queue_waiters[name] -= 1


async def chat(*, purpose: Purpose, messages: list[dict], tools: list | None = None,
               tool_choice=None, max_tokens: int | None = None,
               user_id=None, agency_id=None, conversation_id=None) -> LlmResult:
    r = await _resolve(purpose)
    await _acquire(r.provider_name, r.rate_limit_rps, r.rate_limit_rpm, r.max_queue_size)

    body: dict = {"model": r.model, "messages": messages}
    if tools is not None:
        body["tools"] = tools
    if tool_choice is not None:
        body["tool_choice"] = tool_choice
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if r.request_usage:
        body["usage"] = {"include": True}

    auth_value = f"{r.auth_scheme} {r.api_key}".strip()
    headers = {"Content-Type": "application/json", r.auth_header: auth_value}
    try:
        async with httpx.AsyncClient(timeout=r.timeout) as client:
            resp = await client.post(r.base_url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise LlmError(f"{purpose}: network error: {exc}", provider=r.provider_name, kind="network")
    if resp.status_code != 200:
        raise LlmError(f"{purpose}: provider returned {resp.status_code}",
                       status=resp.status_code, provider=r.provider_name, kind="http")
    data = resp.json()
    msg = (data.get("choices") or [{}])[0].get("message", {})
    usage = data.get("usage") or {}
    info = LlmUsageInfo(
        model=data.get("model") or r.model,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        cost_usd=usage.get("cost"),
    )
    await _record_usage(purpose, info, user_id, agency_id, conversation_id)
    return LlmResult(content=(msg.get("content") or "").strip(),
                     tool_calls=msg.get("tool_calls"), usage=info, raw=data)


@dataclass
class LlmPingResult:
    ok: bool
    latency_ms: int
    model: str | None
    error: str | None


async def ping(purpose: str) -> LlmPingResult:
    """Fire a minimal completion through a purpose's route to prove it works end-to-end.

    Uses the production `chat()` path, so it resolves an enabled route + provider,
    applies auth and rate limits, and records usage. Caps output at one token to keep
    cost negligible. Failures are returned, not raised.
    """
    start = time.monotonic()
    try:
        res = await chat(purpose=purpose, messages=[{"role": "user", "content": "ping"}], max_tokens=1)
        return LlmPingResult(ok=True, latency_ms=_elapsed_ms(start), model=res.usage.model, error=None)
    except LlmError as exc:
        return LlmPingResult(ok=False, latency_ms=_elapsed_ms(start), model=None, error=str(exc))


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


async def _record_usage(purpose, info: LlmUsageInfo, user_id, agency_id, conversation_id) -> None:
    from app.models import LlmUsage
    from app.services.usage_context import current_api_key_id, current_user_id
    try:
        await LlmUsage.create(
            model=info.model, purpose=purpose,
            prompt_tokens=info.prompt_tokens, completion_tokens=info.completion_tokens,
            cost_usd=info.cost_usd,
            user_id=user_id if user_id is not None else current_user_id.get(),
            agency_id=agency_id, conversation_id=conversation_id,
            api_key_id=current_api_key_id.get(),
        )
    except Exception:  # accounting must never break the call path
        logger.exception("failed to record llm usage")
