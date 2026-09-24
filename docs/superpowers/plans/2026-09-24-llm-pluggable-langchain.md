# LLM Pluggable LangChain Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-rolled `httpx` LLM client with a unified, pluggable layer built on LangChain standard interfaces.

**Architecture:** A single public service (`chat` freeform, `parse` structured) resolves a purpose to a DB-configured provider + model, builds a LangChain runnable (`init_chat_model` → structured/tools → `.with_retry` → `.with_fallbacks`) with a Redis `BaseRateLimiter`, invokes it under a usage callback, and maps every error to `LlmError`. Providers plug in via a registry keyed by `kind`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, LangChain (`langchain`, `langchain-core`, `langchain-openai`), Redis, pytest.

**Spec:** `docs/superpowers/specs/2026-09-24-llm-pluggable-langchain-design.md`

## Global Constraints

- TDD mandatory: red → green → refactor. One behavior per test.
- No code comments except Swagger/OpenAPI; self-documenting names (project rule).
- Reply/docstrings in ASD-STE100 Simplified Technical English.
- 15-Factor; feature-based clean architecture (`app/features/llm/…`); dependency rule: feature → core only.
- Full-English API route names; no short forms.
- Work on branch `feat/llm-pluggable-langchain`; never a git worktree.
- Dependencies: `langchain`, `langchain-core` (>= 0.3.49), `langchain-openai`.
- `api_key` masked in every admin response (`MASK` sentinel); a missing/masked key on update keeps the stored key.
- Every admin mutation writes an audit record and calls `resolve.invalidate()`.
- Tests never hit the network: the `ProviderSpec.build_model` seam returns a LangChain fake.
- Commands run from `backend/`: `uv run pytest …`, `uv run alembic …`.

## Review Focus

- **Fallback chain cycle or depth > 3** (binding A → B → A): `resolve.for_purpose` must terminate with a bounded chain, never loop. → Task 9.
- **Unknown / uninstalled provider `kind`**: `providers.get` must raise `LlmError(kind="config")`, not `KeyError`/`ImportError` crash. → Task 3.
- **Structured output fails validation** (model returns malformed object): surfaces as `LlmError(kind="parse")`, not a raw `ValidationError`. → Task 2 + Task 12.
- **Rate-limit queue full under concurrency**: `RedisRateLimiter.aacquire` fast-fails with `LlmError(kind="queue_full")`, never blocks forever. → Task 5.
- **Call consumes tokens then fails**: usage is still recorded (the `finally`), and `usage.record` never masks the real `LlmError`. → Task 12.

---

### Task 1: Add LangChain dependencies

**Files:**
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/test_llm_dependencies.py`

**Interfaces:**
- Produces: importable `langchain`, `langchain_core`, `langchain_openai`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm_dependencies.py
def test_langchain_stack_importable():
    import langchain_core
    from langchain.chat_models import init_chat_model
    from langchain_core.callbacks import get_usage_metadata_callback
    from langchain_core.rate_limiters import BaseRateLimiter
    import langchain_openai
    assert callable(init_chat_model)
    assert tuple(int(p) for p in langchain_core.__version__.split(".")[:3]) >= (0, 3, 49)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_dependencies.py -v`
Expected: FAIL with `ModuleNotFoundError: langchain`.

- [ ] **Step 3: Add the dependencies**

In `backend/pyproject.toml`, under the main `dependencies` array, add:

```toml
    "langchain>=0.3.27",
    "langchain-core>=0.3.49",
    "langchain-openai>=0.3.0",
```

Then install: `uv sync`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_llm_dependencies.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/tests/test_llm_dependencies.py
git commit -m "build(llm): add langchain, langchain-core, langchain-openai"
```

---

### Task 2: `errors.py` — `LlmError` and `to_llm_error`

**Files:**
- Create: `backend/app/features/llm/services/errors.py`
- Test: `backend/tests/services/test_llm_errors.py`

**Interfaces:**
- Produces:
  - `class LlmError(Exception)` with `__init__(self, message, *, kind, status=None, provider=None)` and attributes `kind`, `status`, `provider`.
  - `def to_llm_error(exc: Exception, spec) -> LlmError` where `spec` has `.map_error(exc) -> LlmError | None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/test_llm_errors.py
import httpx
import pytest
from pydantic import BaseModel, ValidationError
from langchain_core.exceptions import OutputParserException
from app.features.llm.services.errors import LlmError, to_llm_error


class _Spec:
    def map_error(self, exc):
        return None


def test_llm_error_passthrough():
    original = LlmError("boom", kind="queue_full")
    assert to_llm_error(original, _Spec()) is original


def test_spec_mapping_wins():
    class Spec:
        def map_error(self, exc):
            return LlmError("mapped", kind="rate_limited")
    assert to_llm_error(RuntimeError("x"), Spec()).kind == "rate_limited"


def test_output_parser_exception_is_parse():
    assert to_llm_error(OutputParserException("bad"), _Spec()).kind == "parse"


def test_validation_error_is_parse():
    class M(BaseModel):
        x: int
    try:
        M(x="not-int")
    except ValidationError as e:
        assert to_llm_error(e, _Spec()).kind == "parse"


def test_httpx_timeout_is_timeout():
    assert to_llm_error(httpx.TimeoutException("t"), _Spec()).kind == "timeout"


def test_httpx_transport_is_network():
    assert to_llm_error(httpx.ConnectError("c"), _Spec()).kind == "network"


def test_unknown_is_unknown():
    assert to_llm_error(RuntimeError("?"), _Spec()).kind == "unknown"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_errors.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# backend/app/features/llm/services/errors.py
import httpx
from pydantic import ValidationError
from langchain_core.exceptions import OutputParserException


class LlmError(Exception):
    def __init__(self, message, *, kind, status=None, provider=None):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.provider = provider


def to_llm_error(exc, spec):
    if isinstance(exc, LlmError):
        return exc
    mapped = spec.map_error(exc)
    if mapped is not None:
        return mapped
    if isinstance(exc, (OutputParserException, ValidationError)):
        return LlmError(str(exc), kind="parse")
    if isinstance(exc, httpx.TimeoutException):
        return LlmError(str(exc), kind="timeout")
    if isinstance(exc, httpx.TransportError):
        return LlmError(str(exc), kind="network")
    return LlmError(str(exc), kind="unknown")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_errors.py -v`
Expected: PASS (all 7).

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/services/errors.py backend/tests/services/test_llm_errors.py
git commit -m "feat(llm): add LlmError and to_llm_error exception mapping"
```

---

### Task 3: `providers.py` — `ProviderSpec`, registry, OpenAI spec

**Files:**
- Create: `backend/app/features/llm/services/providers.py`
- Test: `backend/tests/services/test_llm_providers.py`

**Interfaces:**
- Consumes: `LlmError` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class ProviderSpec` with fields `kind: str`, `model_provider: str`, `transient_errors: tuple[type[Exception], ...]`, `map_error: Callable[[Exception], LlmError | None]`, `build_model: Callable[..., BaseChatModel]`.
  - `def register(spec: ProviderSpec) -> None` (raises `ValueError` on duplicate kind).
  - `def get(kind: str) -> ProviderSpec` (raises `LlmError(kind="config")` if unknown).
  - `def known_kinds() -> tuple[str, ...]`.
  - Registered `openai` spec.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/test_llm_providers.py
import openai
import pytest
from app.features.llm.services import providers
from app.features.llm.services.errors import LlmError


def test_openai_registered():
    assert "openai" in providers.known_kinds()
    spec = providers.get("openai")
    assert spec.model_provider == "openai"


def test_unknown_kind_raises_config():
    with pytest.raises(LlmError) as e:
        providers.get("nope")
    assert e.value.kind == "config"


def test_duplicate_registration_raises():
    spec = providers.get("openai")
    with pytest.raises(ValueError):
        providers.register(spec)


def test_openai_map_error_rate_limit():
    spec = providers.get("openai")
    exc = openai.RateLimitError.__new__(openai.RateLimitError)
    assert spec.map_error(exc).kind == "rate_limited"


def test_openai_map_error_timeout():
    spec = providers.get("openai")
    exc = openai.APITimeoutError.__new__(openai.APITimeoutError)
    assert spec.map_error(exc).kind == "timeout"


def test_openai_map_error_unmapped_returns_none():
    spec = providers.get("openai")
    assert spec.map_error(RuntimeError("x")) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_providers.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# backend/app/features/llm/services/providers.py
from collections.abc import Callable
from dataclasses import dataclass, field

import openai
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.features.llm.services.errors import LlmError


@dataclass(frozen=True)
class ProviderSpec:
    kind: str
    model_provider: str
    transient_errors: tuple[type[Exception], ...]
    map_error: Callable[[Exception], LlmError | None]
    build_model: Callable[..., BaseChatModel] = init_chat_model


_SPECS: dict[str, ProviderSpec] = {}


def register(spec: ProviderSpec) -> None:
    if spec.kind in _SPECS:
        raise ValueError(f"provider kind already registered: {spec.kind!r}")
    _SPECS[spec.kind] = spec


def get(kind: str) -> ProviderSpec:
    spec = _SPECS.get(kind)
    if spec is None:
        raise LlmError(f"unknown provider kind {kind!r}", kind="config")
    return spec


def known_kinds() -> tuple[str, ...]:
    return tuple(_SPECS)


_OPENAI_TRANSIENT = (
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIConnectionError,
)


def _openai_map_error(exc: Exception) -> LlmError | None:
    if isinstance(exc, openai.APITimeoutError):
        return LlmError(str(exc), kind="timeout", provider="openai")
    if isinstance(exc, openai.RateLimitError):
        return LlmError(str(exc), kind="rate_limited", provider="openai")
    if isinstance(exc, openai.APIConnectionError):
        return LlmError(str(exc), kind="network", provider="openai")
    if isinstance(exc, openai.APIStatusError):
        return LlmError(str(exc), kind="provider",
                        status=getattr(exc, "status_code", None), provider="openai")
    return None


register(ProviderSpec(
    kind="openai",
    model_provider="openai",
    transient_errors=_OPENAI_TRANSIENT,
    map_error=_openai_map_error,
))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_providers.py -v`
Expected: PASS (6).

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/services/providers.py backend/tests/services/test_llm_providers.py
git commit -m "feat(llm): add provider registry and openai ProviderSpec"
```

---

### Task 4: `purpose.py` and `result_schemas.py`

**Files:**
- Create: `backend/app/features/llm/services/result_schemas.py`
- Create: `backend/app/features/llm/services/purpose.py`
- Test: `backend/tests/services/test_llm_purpose.py`

**Interfaces:**
- Produces:
  - `class Purpose(StrEnum)`: `CLASSIFICATION`, `BRIEF`, `JUDGE`, `PARSE_SPEC`, `POPULAR_QUESTIONS`.
  - `KNOWN_PURPOSES: tuple[str, ...]`.
  - Result schemas: `ClassificationResult`, `JudgeResult`, `SpecResult` (+ `SpecEndpoint`, `SpecResponseField`), `PopularQuestionsResult` (+ `PopularQuestionItem`).
  - `PURPOSE_SCHEMAS: dict[Purpose, type[BaseModel] | None]`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/test_llm_purpose.py
from app.features.llm.services.purpose import Purpose, KNOWN_PURPOSES, PURPOSE_SCHEMAS
from app.features.llm.services.result_schemas import (
    ClassificationResult, JudgeResult, SpecResult, PopularQuestionsResult,
)


def test_known_purposes():
    assert KNOWN_PURPOSES == (
        "classification", "brief", "judge", "parse_spec", "popular_questions")


def test_schema_map():
    assert PURPOSE_SCHEMAS[Purpose.CLASSIFICATION] is ClassificationResult
    assert PURPOSE_SCHEMAS[Purpose.BRIEF] is None
    assert PURPOSE_SCHEMAS[Purpose.JUDGE] is JudgeResult


def test_judge_result_validates():
    r = JudgeResult(score=0.8, reason="ok")
    assert r.score == 0.8


def test_spec_result_nested():
    r = SpecResult(auth_method="api_key", auth_header="X-API-Key", base_path="/v1",
                   request_format="json",
                   endpoints=[{"method": "GET", "path": "/x", "description": "d"}],
                   response_schema=[{"field": "a", "type": "string", "description": "d"}])
    assert r.endpoints[0].method == "GET"


def test_popular_questions_result():
    r = PopularQuestionsResult(questions=[{"text": "q", "agency_id": None}])
    assert r.questions[0].text == "q"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_purpose.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the schemas**

```python
# backend/app/features/llm/services/result_schemas.py
from typing import Literal

from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    """Category of a Thai government-service question."""
    category: Literal[
        "สอบถามข้อมูล", "ตรวจสอบสถานะ", "ขั้นตอนดำเนินการ",
        "กฎหมาย/ระเบียบ", "ไม่สามารถจัดหมวดหมู่ได้",
    ] = Field(description="The single best-fit category.")


class JudgeResult(BaseModel):
    """Grade of an agency answer against expected topics."""
    score: float = Field(description="Quality score from 0.0 to 1.0.")
    reason: str = Field(default="", description="Short justification for the score.")


class SpecEndpoint(BaseModel):
    """One API endpoint found in a specification."""
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    path: str
    description: str


class SpecResponseField(BaseModel):
    """One common response field found across endpoints."""
    field: str = Field(description="Field name or dot path, e.g. data.items[].name.")
    type: str = Field(description="Data type: string, number, boolean, array, object, date.")
    description: str
    example: str | None = None


class SpecResult(BaseModel):
    """Structured API specification extracted from a document."""
    auth_method: Literal["api_key", "oauth2", "basic_auth", "none"]
    auth_header: str = Field(description="Auth header name, e.g. X-API-Key.")
    base_path: str = Field(description="Base path prefix, e.g. /api/v1.")
    request_format: Literal["json", "xml"]
    endpoints: list[SpecEndpoint]
    response_schema: list[SpecResponseField]


class PopularQuestionItem(BaseModel):
    """One synthesized popular question."""
    text: str
    agency_id: str | None = None


class PopularQuestionsResult(BaseModel):
    """The set of synthesized popular questions."""
    questions: list[PopularQuestionItem]
```

- [ ] **Step 4: Implement the purpose module**

```python
# backend/app/features/llm/services/purpose.py
from enum import StrEnum

from pydantic import BaseModel

from app.features.llm.services.result_schemas import (
    ClassificationResult, JudgeResult, PopularQuestionsResult, SpecResult,
)


class Purpose(StrEnum):
    CLASSIFICATION = "classification"
    BRIEF = "brief"
    JUDGE = "judge"
    PARSE_SPEC = "parse_spec"
    POPULAR_QUESTIONS = "popular_questions"


KNOWN_PURPOSES = tuple(p.value for p in Purpose)

PURPOSE_SCHEMAS: dict[Purpose, type[BaseModel] | None] = {
    Purpose.CLASSIFICATION: ClassificationResult,
    Purpose.BRIEF: None,
    Purpose.JUDGE: JudgeResult,
    Purpose.PARSE_SPEC: SpecResult,
    Purpose.POPULAR_QUESTIONS: PopularQuestionsResult,
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_purpose.py -v`
Expected: PASS (5).

- [ ] **Step 6: Commit**

```bash
git add backend/app/features/llm/services/purpose.py backend/app/features/llm/services/result_schemas.py backend/tests/services/test_llm_purpose.py
git commit -m "feat(llm): add Purpose enum and per-purpose result schemas"
```

---

### Task 5: `rate_limit.py` — `RedisRateLimiter`

**Files:**
- Create: `backend/app/features/llm/services/rate_limit.py`
- Test: `backend/tests/services/test_llm_rate_limit.py`

**Interfaces:**
- Consumes: `LlmError` (Task 2); the existing rate-limit counter repo (`app/features/llm/repositories/rate_limit.py`) — reuse its `check(key, limit, window_s)` style if present, otherwise a token-bucket over `rate_limit_counters`. This task depends only on a `check`-like coroutine; the concrete counter store is the existing one.
- Produces:
  - `class RedisRateLimiter(BaseRateLimiter)` built with `(provider_name, rps, rpm, max_queue_size)`; `async def aacquire(self, *, blocking=True) -> bool`; `def acquire(self, *, blocking=True) -> bool` (raises `NotImplementedError`).
  - `def limiter_for(resolved) -> RedisRateLimiter` (cached per provider name); `def reset_cache() -> None` (test helper).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/test_llm_rate_limit.py
import pytest
from app.features.llm.services.errors import LlmError
from app.features.llm.services import rate_limit


class _FakeWindow:
    def __init__(self, allow_first_n):
        self.allow_first_n = allow_first_n
        self.calls = 0

    async def allow(self, key, limit, window_s):
        self.calls += 1
        return self.calls <= self.allow_first_n


@pytest.mark.asyncio
async def test_aacquire_allows_within_limit(monkeypatch):
    window = _FakeWindow(allow_first_n=10)
    monkeypatch.setattr(rate_limit, "_allow", window.allow)
    limiter = rate_limit.RedisRateLimiter("p", rps=5, rpm=100, max_queue_size=10)
    assert await limiter.aacquire() is True


@pytest.mark.asyncio
async def test_aacquire_queue_full_fast_fails(monkeypatch):
    async def never(key, limit, window_s):
        return False
    monkeypatch.setattr(rate_limit, "_allow", never)
    limiter = rate_limit.RedisRateLimiter("p", rps=1, rpm=1, max_queue_size=0)
    with pytest.raises(LlmError) as e:
        await limiter.aacquire()
    assert e.value.kind == "queue_full"


def test_sync_acquire_unsupported():
    limiter = rate_limit.RedisRateLimiter("p", rps=1, rpm=1, max_queue_size=1)
    with pytest.raises(NotImplementedError):
        limiter.acquire()


def test_no_limits_is_noop(monkeypatch):
    limiter = rate_limit.RedisRateLimiter("p", rps=None, rpm=None, max_queue_size=10)
    import asyncio
    assert asyncio.get_event_loop().run_until_complete(limiter.aacquire()) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_rate_limit.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# backend/app/features/llm/services/rate_limit.py
import asyncio
from collections import defaultdict

from langchain_core.rate_limiters import BaseRateLimiter

from app.core.db import AsyncSessionLocal
from app.features.llm.repositories import rate_limit as rate_limit_repo
from app.features.llm.services.errors import LlmError

_queue_waiters: dict[str, int] = defaultdict(int)


async def _allow(key: str, limit: int, window_s: float) -> bool:
    async with AsyncSessionLocal() as session, session.begin():
        result = await rate_limit_repo.check(session, key, limit=limit, window_s=window_s)
    return result.allowed


class RedisRateLimiter(BaseRateLimiter):
    def __init__(self, provider_name, rps, rpm, max_queue_size):
        self.provider_name = provider_name
        self.rps = rps
        self.rpm = rpm
        self.max_queue_size = max_queue_size

    def acquire(self, *, blocking: bool = True) -> bool:
        raise NotImplementedError("RedisRateLimiter is async-only; use aacquire")

    async def aacquire(self, *, blocking: bool = True) -> bool:
        if not self.rps and not self.rpm:
            return True
        name = self.provider_name
        if _queue_waiters[name] >= self.max_queue_size:
            raise LlmError(f"provider {name!r} rate-limit queue is full",
                           kind="queue_full", provider=name)
        _queue_waiters[name] += 1
        try:
            while True:
                if self.rps and not await _allow(f"llm:{name}:s", self.rps, 1.0):
                    await asyncio.sleep(0.02)
                    continue
                if self.rpm and not await _allow(f"llm:{name}:m", self.rpm, 60.0):
                    await asyncio.sleep(0.02)
                    continue
                return True
        finally:
            _queue_waiters[name] -= 1


_cache: dict[str, RedisRateLimiter] = {}


def limiter_for(resolved) -> RedisRateLimiter:
    existing = _cache.get(resolved.provider_name)
    if existing is not None:
        return existing
    limiter = RedisRateLimiter(resolved.provider_name, resolved.rate_limit_rps,
                               resolved.rate_limit_rpm, resolved.max_queue_size)
    _cache[resolved.provider_name] = limiter
    return limiter


def reset_cache() -> None:
    _cache.clear()
    _queue_waiters.clear()
```

Note: confirm the existing `rate_limit_repo.check(session, key, *, limit, window_s)` signature and its `.allowed` attribute during implementation; the current client used `_provider_limiter.check(key, limit=…, window_s=…)` returning an object with `.allowed`. Adapt `_allow` to match the real signature if it differs.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_rate_limit.py -v`
Expected: PASS (4).

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/services/rate_limit.py backend/tests/services/test_llm_rate_limit.py
git commit -m "feat(llm): add distributed RedisRateLimiter (BaseRateLimiter)"
```

---

### Task 6: New models `LlmProvider`, `LlmBinding`, `LlmUsage`

**Files:**
- Create: `backend/app/features/llm/models/llm_provider.py` (replace contents)
- Create: `backend/app/features/llm/models/llm_binding.py`
- Modify: `backend/app/features/llm/models/llm_usage.py` (keep; verify columns)
- Modify: `backend/app/features/llm/models/__init__.py`
- Test: `backend/tests/services/test_llm_models.py` (replace)

**Interfaces:**
- Produces ORM classes on `Base.metadata`: `LlmProvider` (`__tablename__="llm_provider"`), `LlmBinding` (`__tablename__="llm_binding"`), `LlmUsage` (`__tablename__="llm_usage"`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_llm_models.py
from app.features.llm.models.llm_provider import LlmProvider
from app.features.llm.models.llm_binding import LlmBinding
from app.features.llm.models.llm_usage import LlmUsage


def test_provider_columns():
    cols = set(LlmProvider.__table__.columns.keys())
    assert {"provider", "model", "base_url", "api_key", "max_retries",
            "rate_limit_rps", "rate_limit_rpm", "max_queue_size", "enabled"} <= cols
    assert "auth_header" not in cols and "auth_scheme" not in cols


def test_binding_columns():
    cols = set(LlmBinding.__table__.columns.keys())
    assert {"purpose", "provider_id", "model_override",
            "fallback_binding_id", "timeout_override", "enabled"} <= cols


def test_usage_total_tokens_property():
    u = LlmUsage(model="m", purpose="brief", prompt_tokens=3, completion_tokens=4)
    assert u.total_tokens == 7
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_models.py -v`
Expected: FAIL (import of `llm_binding` missing, or old provider columns present).

- [ ] **Step 3: Implement `LlmProvider`**

```python
# backend/app/features/llm/models/llm_provider.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base
from app.core.utils import generate_uuid


class LlmProvider(Base):
    __tablename__ = "llm_provider"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    provider: Mapped[str] = mapped_column(String(50), default="openai")
    model: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str] = mapped_column(Text, default="")
    timeout_seconds: Mapped[float] = mapped_column(Float, default=60.0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    rate_limit_rps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_queue_size: Mapped[int] = mapped_column(Integer, default=50)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 4: Implement `LlmBinding`**

```python
# backend/app/features/llm/models/llm_binding.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base
from app.core.utils import generate_uuid


class LlmBinding(Base):
    __tablename__ = "llm_binding"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    purpose: Mapped[str] = mapped_column(String(50), unique=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_provider.id", ondelete="RESTRICT"), nullable=False)
    model_override: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fallback_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_binding.id", ondelete="SET NULL"), nullable=True)
    timeout_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 5: Update `LlmUsage` and models `__init__`**

Set `LlmUsage.__tablename__ = "llm_usage"` (already), keep its columns. In `backend/app/features/llm/models/__init__.py`, replace the old `llm_route` import with:

```python
from app.features.llm.models.llm_provider import LlmProvider
from app.features.llm.models.llm_binding import LlmBinding
from app.features.llm.models.llm_usage import LlmUsage

__all__ = ["LlmProvider", "LlmBinding", "LlmUsage"]
```

Delete `backend/app/features/llm/models/llm_route.py`.

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_models.py -v`
Expected: PASS (3).

- [ ] **Step 7: Commit**

```bash
git add backend/app/features/llm/models/ backend/tests/services/test_llm_models.py
git rm backend/app/features/llm/models/llm_route.py
git commit -m "feat(llm): reshape models to llm_provider/llm_binding/llm_usage"
```

---

### Task 7: Migration `0006`

**Files:**
- Create: `backend/alembic/versions/0006_llm_pluggable_langchain.py`
- Test: `backend/tests/test_migration_0006.py`

**Interfaces:**
- Produces DB tables `llm_provider`, `llm_binding`, `llm_usage` matching Task 6 models.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_migration_0006.py
from sqlalchemy import inspect
from app.features.llm.models.llm_provider import LlmProvider  # noqa: F401
from app.features.llm.models.llm_binding import LlmBinding    # noqa: F401


def test_tables_exist_after_upgrade(db_engine_sync):
    names = inspect(db_engine_sync).get_table_names()
    assert {"llm_provider", "llm_binding", "llm_usage"} <= set(names)
```

Use the existing test fixture that runs `alembic upgrade head` (match the fixture name used by other migration/DB tests in `tests/conftest.py`; if the suite runs migrations in a container fixture, assert against that engine).

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_migration_0006.py -v`
Expected: FAIL (tables absent — revision not written).

- [ ] **Step 3: Autogenerate then hand-verify**

Run: `uv run alembic revision --autogenerate -m "llm pluggable langchain"` and rename the file to `0006_llm_pluggable_langchain.py`, `down_revision = "0005"`. Verify the upgrade creates `llm_provider`, `llm_binding` (with the self-FK `fallback_binding_id` via `use_alter=True` or a post-create FK), `llm_usage`; and that it drops the old `llm_providers`/`llm_routes` tables. Downgrade drops the three new tables (and, if you want reversibility, recreates the old ones — otherwise document the downgrade as forward-only for these).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_migration_0006.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0006_llm_pluggable_langchain.py backend/tests/test_migration_0006.py
git commit -m "feat(llm): migration 0006 creates llm_provider/llm_binding/llm_usage"
```

---

### Task 8: Repositories

**Files:**
- Create: `backend/app/features/llm/repositories/llm.py` (replace contents)
- Modify: `backend/app/features/llm/repositories/llm_usage.py` (keep `create`)
- Test: `backend/tests/test_llm_repository.py` (replace)

**Interfaces:**
- Produces (all `async`, `session`-first):
  - Providers: `list_providers`, `create_provider(**data)`, `get_provider(id)`, `update_provider(provider, data)`, `delete_provider(provider)`, `provider_has_bindings(provider_id) -> bool`.
  - Bindings: `list_bindings`, `create_binding(**data)`, `get_binding(id)`, `get_binding_by_purpose(purpose)`, `enabled_binding_for_purpose(purpose)`, `binding_purpose_exists(purpose, exclude_id=None) -> bool`, `update_binding(binding, data)`, `delete_binding(binding)`.
  - `llm_usage_repo.create(session, *, model, purpose, prompt_tokens, completion_tokens, cost_usd, user_id, agency_id, conversation_id)`.

- [ ] **Step 1: Write the failing tests** — mirror the existing `test_llm_repository.py` cases against the new names/tables: create a provider, create a binding referencing it, `enabled_binding_for_purpose` returns it, `binding_purpose_exists` true/false, `provider_has_bindings` true when a binding points at it, delete guards. (Reuse the DB session fixture the current repo test uses.)

```python
# backend/tests/test_llm_repository.py  (representative core cases)
import pytest
from app.features.llm.repositories import llm as repo


@pytest.mark.asyncio
async def test_enabled_binding_for_purpose(db_session):
    p = await repo.create_provider(db_session, name="p1", provider="openai",
                                   model="gpt-4o-mini", api_key="k")
    await repo.create_binding(db_session, purpose="brief", provider_id=p.id)
    got = await repo.enabled_binding_for_purpose(db_session, "brief")
    assert got is not None and got.provider_id == p.id


@pytest.mark.asyncio
async def test_provider_has_bindings_guard(db_session):
    p = await repo.create_provider(db_session, name="p2", provider="openai",
                                   model="m", api_key="k")
    await repo.create_binding(db_session, purpose="judge", provider_id=p.id)
    assert await repo.provider_has_bindings(db_session, p.id) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_llm_repository.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** the repo functions with SQLAlchemy 2 async `select`/`delete`, following the existing repo style (module-level, `session` first). `enabled_binding_for_purpose` filters `purpose == p, enabled.is_(True)`. `binding_purpose_exists` uses `exists()` with optional `id != exclude_id`. `provider_has_bindings` checks any binding with `provider_id == id`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_llm_repository.py tests/test_llm_usage_repository.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/repositories/ backend/tests/test_llm_repository.py
git commit -m "feat(llm): repositories for providers and bindings"
```

---

### Task 9: `resolve.py` — `ResolvedRoute`, `for_purpose`, cache

**Files:**
- Create: `backend/app/features/llm/services/resolve.py`
- Test: `backend/tests/services/test_llm_resolve.py` (replace old `test_llm_client_resolve.py`)

**Interfaces:**
- Consumes: `llm` repo (Task 8), `LlmError` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class ResolvedRoute` (fields per spec §6, incl. `fallback: ResolvedRoute | None`).
  - `async def for_purpose(session, purpose) -> ResolvedRoute` (30s cache).
  - `def invalidate() -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/test_llm_resolve.py
import pytest
from app.features.llm.services import resolve
from app.features.llm.services.errors import LlmError


@pytest.mark.asyncio
async def test_no_binding_is_config_error(db_session):
    resolve.invalidate()
    with pytest.raises(LlmError) as e:
        await resolve.for_purpose(db_session, "brief")
    assert e.value.kind == "config"


@pytest.mark.asyncio
async def test_resolves_with_fallback_chain(db_session, make_binding):
    # make_binding is a fixture that creates provider+binding rows; see helper below
    primary = await make_binding("judge", model="a")
    fb = await make_binding("judge_fb", model="b")
    await set_fallback(db_session, primary, fb)          # helper sets fallback_binding_id
    resolve.invalidate()
    r = await resolve.for_purpose(db_session, "judge")
    assert r.model == "a"
    assert r.fallback is not None and r.fallback.model == "b"


@pytest.mark.asyncio
async def test_cycle_is_bounded(db_session, make_binding):
    a = await make_binding("p_a", model="a")
    b = await make_binding("p_b", model="b")
    await set_fallback(db_session, a, b)
    await set_fallback(db_session, b, a)                 # A -> B -> A
    resolve.invalidate()
    r = await resolve.for_purpose(db_session, "p_a")
    # chain terminates; depth <= 3, no infinite loop
    depth = 0
    node = r
    while node is not None:
        depth += 1
        node = node.fallback
    assert depth <= 3
```

Add shared fixtures in `backend/tests/services/conftest.py` (Tasks 9, 12, 15, 16 reuse them):

```python
# backend/tests/services/conftest.py
import pytest
from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services import rate_limit, resolve


@pytest.fixture(autouse=True)
def _reset_llm_caches():
    resolve.invalidate()
    rate_limit.reset_cache()
    yield
    resolve.invalidate()
    rate_limit.reset_cache()


@pytest.fixture
def make_binding(db_session):
    async def _make(purpose, *, kind="openai", model="m"):
        provider = await llm_repo.create_provider(
            db_session, name=f"prov-{purpose}", provider=kind, model=model, api_key="k")
        return await llm_repo.create_binding(
            db_session, purpose=purpose, provider_id=provider.id)
    return _make


@pytest.fixture
def set_fallback(db_session):
    async def _set(binding, fallback):
        await llm_repo.update_binding(
            db_session, binding, {"fallback_binding_id": fallback.id})
    return _set
```

In the resolve tests, `await make_binding(...)` / `await set_fallback(binding, fb)`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_resolve.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# backend/app/features/llm/services/resolve.py
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services.errors import LlmError

_CACHE_TTL_S = 30.0
_MAX_FALLBACK_DEPTH = 3


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
    fallback: "ResolvedRoute | None"


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
    resolved = await _build(session, binding, seen=set(), depth=0)
    _cache[purpose] = (resolved, time.monotonic())
    return resolved


async def _build(session, binding, *, seen: set, depth: int) -> ResolvedRoute:
    provider = await llm_repo.get_provider(session, binding.provider_id)
    if provider is None or not provider.enabled:
        raise LlmError("provider missing or disabled", kind="config",
                       provider=getattr(provider, "name", None))
    fallback = None
    if (binding.fallback_binding_id is not None
            and binding.fallback_binding_id not in seen
            and depth + 1 < _MAX_FALLBACK_DEPTH):
        seen = seen | {binding.id}
        fb_binding = await llm_repo.get_binding(session, binding.fallback_binding_id)
        if fb_binding is not None and fb_binding.enabled and fb_binding.id not in seen:
            fallback = await _build(session, fb_binding, seen=seen, depth=depth + 1)
    return ResolvedRoute(
        provider_name=provider.name, kind=provider.provider,
        model=binding.model_override or provider.model,
        base_url=provider.base_url, api_key=provider.api_key,
        timeout=binding.timeout_override or provider.timeout_seconds,
        max_retries=provider.max_retries,
        rate_limit_rps=provider.rate_limit_rps, rate_limit_rpm=provider.rate_limit_rpm,
        max_queue_size=provider.max_queue_size, fallback=fallback,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_resolve.py -v`
Expected: PASS (3).

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/services/resolve.py backend/tests/services/test_llm_resolve.py
git rm backend/tests/services/test_llm_client_resolve.py
git commit -m "feat(llm): resolve purpose to provider with bounded fallback chain"
```

---

### Task 10: `model_factory.py` — `build`

**Files:**
- Create: `backend/app/features/llm/services/model_factory.py`
- Test: `backend/tests/services/test_llm_model_factory.py`

**Interfaces:**
- Consumes: `providers` (Task 3), `rate_limit` (Task 5), `ResolvedRoute` (Task 9).
- Produces: `def build(resolved, *, schema=None, tools=None, tool_choice=None) -> Runnable`.

- [ ] **Step 1: Write the failing test** — use a fake `build_model` on a registered test spec so no network:

```python
# backend/tests/services/test_llm_model_factory.py
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from app.features.llm.services import providers, model_factory, rate_limit
from app.features.llm.services.providers import ProviderSpec
from app.features.llm.services.errors import LlmError
from app.features.llm.services.resolve import ResolvedRoute


@pytest.fixture
def fake_kind():
    def build_model(model, **kwargs):
        return GenericFakeChatModel(messages=iter([AIMessage(content="hi")]))
    spec = ProviderSpec(kind="faker", model_provider="openai",
                        transient_errors=(), map_error=lambda e: None,
                        build_model=build_model)
    if "faker" not in providers.known_kinds():
        providers.register(spec)
    rate_limit.reset_cache()
    yield


def _route(**kw):
    base = dict(provider_name="p", kind="faker", model="m", base_url=None, api_key="k",
                timeout=30.0, max_retries=2, rate_limit_rps=None, rate_limit_rpm=None,
                max_queue_size=10, fallback=None)
    base.update(kw)
    return ResolvedRoute(**base)


@pytest.mark.asyncio
async def test_build_invokes(fake_kind):
    runnable = model_factory.build(_route())
    out = await runnable.ainvoke([{"role": "user", "content": "hey"}])
    assert isinstance(out, AIMessage)


@pytest.mark.asyncio
async def test_fallback_used_when_primary_fails(fake_kind):
    def boom_model(model, **kwargs):
        class Boom:
            async def ainvoke(self, *a, **k):
                raise RuntimeError("primary down")
            def with_retry(self, **k):
                return self
            def with_fallbacks(self, fbs):
                return fbs[0]
        return Boom()
    providers.register(ProviderSpec(kind="boom", model_provider="openai",
                                    transient_errors=(RuntimeError,),
                                    map_error=lambda e: None, build_model=boom_model))
    r = _route(kind="boom", fallback=_route(kind="faker"))
    runnable = model_factory.build(r)
    out = await runnable.ainvoke([{"role": "user", "content": "hey"}])
    assert out.content == "hi"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_model_factory.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# backend/app/features/llm/services/model_factory.py
from langchain_core.runnables import Runnable

from app.features.llm.services import providers, rate_limit


def build(resolved, *, schema=None, tools=None, tool_choice=None) -> Runnable:
    spec = providers.get(resolved.kind)
    model = spec.build_model(
        resolved.model,
        model_provider=spec.model_provider,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
        timeout=resolved.timeout,
        max_retries=0,
        rate_limiter=rate_limit.limiter_for(resolved),
    )
    if tools:
        model = model.bind_tools(tools, tool_choice=tool_choice)
    if schema:
        model = model.with_structured_output(schema)
    runnable = model.with_retry(
        retry_if_exception_type=spec.transient_errors or (Exception,),
        stop_after_attempt=resolved.max_retries + 1,
        wait_exponential_jitter=True,
    )
    if resolved.fallback is not None:
        runnable = runnable.with_fallbacks(
            [build(resolved.fallback, schema=schema, tools=tools, tool_choice=tool_choice)])
    return runnable
```

Note: `build_model` for the real `openai` kind is `init_chat_model`, which accepts `rate_limiter`, `api_key`, `base_url`, `timeout`, `max_retries`. Fakes ignore extra kwargs. Confirm `with_retry` with `retry_if_exception_type=()` is valid; if empty tuple is rejected, keep the `or (Exception,)` guard as written.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_model_factory.py -v`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/services/model_factory.py backend/tests/services/test_llm_model_factory.py
git commit -m "feat(llm): model_factory assembles runnable with retry and fallbacks"
```

---

### Task 11: `usage.py` — record from the callback aggregate

**Files:**
- Create: `backend/app/features/llm/services/usage.py` (replace contents)
- Test: `backend/tests/services/test_llm_usage_record.py`

**Interfaces:**
- Consumes: `llm_usage_repo.create` (Task 8).
- Produces: `async def record(session, usage_metadata: dict, *, purpose, user_id=None, agency_id=None, conversation_id=None) -> None` where `usage_metadata` is `{model_name: {"input_tokens": int, "output_tokens": int, ...}}` (the `get_usage_metadata_callback().usage_metadata` shape).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/services/test_llm_usage_record.py
import pytest
from app.features.llm.services import usage


class _Repo:
    def __init__(self):
        self.rows = []
    async def create(self, session, **kw):
        self.rows.append(kw)


@pytest.mark.asyncio
async def test_record_one_model(monkeypatch):
    repo = _Repo()
    monkeypatch.setattr(usage, "llm_usage_repo", repo)
    await usage.record(None, {"gpt-4o-mini": {"input_tokens": 5, "output_tokens": 7}},
                       purpose="brief")
    assert repo.rows[0]["model"] == "gpt-4o-mini"
    assert repo.rows[0]["prompt_tokens"] == 5
    assert repo.rows[0]["completion_tokens"] == 7


@pytest.mark.asyncio
async def test_record_empty_is_noop(monkeypatch):
    repo = _Repo()
    monkeypatch.setattr(usage, "llm_usage_repo", repo)
    await usage.record(None, {}, purpose="brief")
    assert repo.rows == []


@pytest.mark.asyncio
async def test_record_swallows_errors(monkeypatch):
    class Boom:
        async def create(self, *a, **k):
            raise RuntimeError("db down")
    monkeypatch.setattr(usage, "llm_usage_repo", Boom())
    await usage.record(None, {"m": {"input_tokens": 1, "output_tokens": 1}}, purpose="brief")
    # no exception raised
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_usage_record.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# backend/app/features/llm/services/usage.py
import logging

from app.features.llm.repositories import llm_usage as llm_usage_repo

logger = logging.getLogger(__name__)


async def record(session, usage_metadata, *, purpose, user_id=None,
                 agency_id=None, conversation_id=None) -> None:
    from app.core.usage_context import current_user_id
    try:
        for model, tokens in (usage_metadata or {}).items():
            await llm_usage_repo.create(
                session,
                model=model, purpose=purpose,
                prompt_tokens=tokens.get("input_tokens", 0),
                completion_tokens=tokens.get("output_tokens", 0),
                cost_usd=tokens.get("cost"),
                user_id=user_id if user_id is not None else current_user_id.get(),
                agency_id=agency_id, conversation_id=conversation_id,
            )
    except Exception:
        logger.exception("failed to record llm usage")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_usage_record.py -v`
Expected: PASS (3).

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/services/usage.py backend/tests/services/test_llm_usage_record.py
git commit -m "feat(llm): record usage from get_usage_metadata_callback aggregate"
```

---

### Task 12: `service.py` — `chat`, `parse`, `ping`

**Files:**
- Create: `backend/app/features/llm/services/service.py`
- Test: `backend/tests/services/test_llm_service.py` (replaces `test_llm_client_chat.py`)

**Interfaces:**
- Consumes: `resolve`, `model_factory`, `providers`, `usage`, `errors`, `purpose`.
- Produces:
  - `async def chat(session, purpose, messages, *, tools=None, tool_choice=None, max_tokens=None, user_id=None, agency_id=None, conversation_id=None) -> AIMessage`.
  - `async def parse(session, purpose, messages, *, schema=None, max_tokens=None, user_id=None, agency_id=None, conversation_id=None) -> BaseModel`.
  - `async def ping(session, purpose) -> LlmPingResult` with `@dataclass class LlmPingResult(ok, latency_ms, model, error)`.

- [ ] **Step 1: Write the failing tests** — register a fake kind whose model returns a canned `AIMessage`, and for `parse` a stub whose `with_structured_output` yields the schema instance. Assert usage recorded and errors mapped.

```python
# backend/tests/services/test_llm_service.py
import pytest
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from app.features.llm.services import providers, service, rate_limit
from app.features.llm.services.providers import ProviderSpec
from app.features.llm.services.errors import LlmError
from app.features.llm.services.purpose import Purpose


@pytest.fixture
def fake_openai(monkeypatch, db_session, make_binding):
    def build_model(model, **kwargs):
        return GenericFakeChatModel(messages=iter([AIMessage(content="answer")]))
    if "fk" not in providers.known_kinds():
        providers.register(ProviderSpec(kind="fk", model_provider="openai",
                                        transient_errors=(), map_error=lambda e: None,
                                        build_model=build_model))
    rate_limit.reset_cache()
    yield build_model


@pytest.mark.asyncio
async def test_chat_returns_aimessage(db_session, fake_openai, make_binding):
    await make_binding("brief", kind="fk")
    out = await service.chat(db_session, Purpose.BRIEF,
                             [{"role": "user", "content": "hi"}])
    assert out.content == "answer"


@pytest.mark.asyncio
async def test_schema_and_tools_together_rejected(db_session, fake_openai, make_binding):
    await make_binding("brief", kind="fk")
    with pytest.raises(LlmError) as e:
        await service._run(db_session, Purpose.BRIEF, [], schema=object, tools=[{}],
                           tool_choice=None, max_tokens=None,
                           user_id=None, agency_id=None, conversation_id=None)
    assert e.value.kind == "config"


@pytest.mark.asyncio
async def test_failure_maps_to_llm_error_and_records_usage(db_session, make_binding, monkeypatch):
    from langchain_core.messages import AIMessage
    recorded = {}

    async def spy_record(session, metadata, **kw):
        recorded["called"] = True
    monkeypatch.setattr(service.usage, "record", spy_record)

    def boom_model(model, **kwargs):
        class Boom:
            async def ainvoke(self, *a, **k):
                raise RuntimeError("down")
            def with_retry(self, **k):
                return self
            def with_fallbacks(self, fbs):
                return self
            def bind(self, **k):
                return self
        return Boom()
    from app.features.llm.services.providers import ProviderSpec
    if "boomsvc" not in providers.known_kinds():
        providers.register(ProviderSpec(kind="boomsvc", model_provider="openai",
                                        transient_errors=(RuntimeError,),
                                        map_error=lambda e: None, build_model=boom_model))
    rate_limit.reset_cache()
    await make_binding("brief", kind="boomsvc")
    with pytest.raises(LlmError):
        await service.chat(db_session, Purpose.BRIEF, [{"role": "user", "content": "x"}])
    assert recorded.get("called") is True   # usage.record ran in the finally
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# backend/app/features/llm/services/service.py
import time
from dataclasses import dataclass

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.features.llm.services import model_factory, providers, resolve, usage
from app.features.llm.services.errors import LlmError, to_llm_error
from app.features.llm.services.purpose import PURPOSE_SCHEMAS, Purpose


async def _run(session, purpose, messages, *, schema, tools, tool_choice, max_tokens,
               user_id, agency_id, conversation_id):
    if schema is not None and tools is not None:
        raise LlmError("schema and tools are mutually exclusive", kind="config")
    resolved = await resolve.for_purpose(session, purpose)
    spec = providers.get(resolved.kind)
    runnable = model_factory.build(resolved, schema=schema, tools=tools, tool_choice=tool_choice)
    if max_tokens is not None:
        runnable = runnable.bind(max_tokens=max_tokens)
    cb_metadata = {}
    try:
        with get_usage_metadata_callback() as cb:
            out = await runnable.ainvoke(messages)
            cb_metadata = cb.usage_metadata
        return out
    except Exception as exc:
        raise to_llm_error(exc, spec)
    finally:
        await usage.record(session, cb_metadata, purpose=str(purpose),
                           user_id=user_id, agency_id=agency_id,
                           conversation_id=conversation_id)


async def chat(session, purpose, messages, *, tools=None, tool_choice=None,
               max_tokens=None, user_id=None, agency_id=None,
               conversation_id=None) -> AIMessage:
    return await _run(session, purpose, messages, schema=None, tools=tools,
                      tool_choice=tool_choice, max_tokens=max_tokens, user_id=user_id,
                      agency_id=agency_id, conversation_id=conversation_id)


async def parse(session, purpose, messages, *, schema=None, max_tokens=None,
                user_id=None, agency_id=None, conversation_id=None) -> BaseModel:
    schema = schema or PURPOSE_SCHEMAS.get(Purpose(purpose))
    if schema is None:
        raise LlmError(f"purpose {purpose!r} has no result schema", kind="config")
    return await _run(session, purpose, messages, schema=schema, tools=None,
                      tool_choice=None, max_tokens=max_tokens, user_id=user_id,
                      agency_id=agency_id, conversation_id=conversation_id)


@dataclass
class LlmPingResult:
    ok: bool
    latency_ms: int
    model: str | None
    error: str | None


async def ping(session, purpose) -> LlmPingResult:
    start = time.monotonic()
    try:
        schema = PURPOSE_SCHEMAS.get(Purpose(purpose))
        if schema is None:
            out = await chat(session, purpose, [{"role": "user", "content": "ping"}], max_tokens=1)
            model = getattr(out, "response_metadata", {}).get("model_name")
        else:
            await parse(session, purpose, [{"role": "user", "content": "ping"}], max_tokens=1)
            model = None
        return LlmPingResult(ok=True, latency_ms=_ms(start), model=model, error=None)
    except LlmError as exc:
        return LlmPingResult(ok=False, latency_ms=_ms(start), model=None, error=str(exc))


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/services/service.py backend/tests/services/test_llm_service.py
git rm backend/tests/services/test_llm_client_chat.py backend/tests/services/test_llm_client_queue.py
git commit -m "feat(llm): public chat/parse/ping service on LangChain"
```

---

### Task 13: Public exports and delete `client.py`

**Files:**
- Modify: `backend/app/features/llm/services/__init__.py` (replace)
- Delete: `backend/app/features/llm/services/client.py`
- Test: `backend/tests/services/test_llm_public_api.py`

**Interfaces:**
- Produces public names: `chat`, `parse`, `ping`, `Purpose`, `KNOWN_PURPOSES`, `LlmError`, `LlmPingResult`, `invalidate`, and the result schemas.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_llm_public_api.py
def test_public_surface():
    from app.features.llm.services import (
        chat, parse, ping, Purpose, KNOWN_PURPOSES, LlmError, invalidate,
        ClassificationResult, JudgeResult, SpecResult, PopularQuestionsResult,
    )
    assert callable(chat) and callable(parse)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_public_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `__init__.py`**

```python
# backend/app/features/llm/services/__init__.py
from app.features.llm.services.errors import LlmError
from app.features.llm.services.providers import known_kinds
from app.features.llm.services.purpose import KNOWN_PURPOSES, Purpose, PURPOSE_SCHEMAS
from app.features.llm.services.resolve import invalidate
from app.features.llm.services.result_schemas import (
    ClassificationResult, JudgeResult, PopularQuestionItem, PopularQuestionsResult,
    SpecEndpoint, SpecResponseField, SpecResult,
)
from app.features.llm.services.service import LlmPingResult, chat, parse, ping

__all__ = [
    "chat", "parse", "ping", "Purpose", "KNOWN_PURPOSES", "PURPOSE_SCHEMAS",
    "LlmError", "LlmPingResult", "invalidate", "known_kinds",
    "ClassificationResult", "JudgeResult", "SpecResult", "SpecEndpoint",
    "SpecResponseField", "PopularQuestionsResult", "PopularQuestionItem",
]
```

Delete `client.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_public_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/services/__init__.py backend/tests/services/test_llm_public_api.py
git rm backend/app/features/llm/services/client.py
git commit -m "feat(llm): public service exports; remove old client"
```

---

### Task 14: Seed defaults

**Files:**
- Modify: `backend/app/features/llm/services/seed.py`
- Test: `backend/tests/services/test_llm_seed.py` (update)

**Interfaces:**
- Produces: `async def seed_llm_defaults(session)` creating one `openai` provider (from env) and one enabled binding per purpose, idempotent.

- [ ] **Step 1: Update the failing test** — assert a seeded provider has `provider == "openai"` and there is an enabled binding for `classification`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/services/test_llm_seed.py -v`

- [ ] **Step 3: Implement** — rewrite `seed_llm_defaults` to create an `LlmProvider(provider="openai", model=<env default>, base_url=<env>, api_key=<env>)` if none exists, then a binding per `Purpose` pointing at it if absent. Read config from `settings` (add `LLM_DEFAULT_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` if not already present in `app/core/config.py`; env-driven per 15-factor). No `auth_header`/`auth_scheme`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/services/test_llm_seed.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/llm/services/seed.py backend/app/core/config.py backend/tests/services/test_llm_seed.py
git commit -m "feat(llm): seed openai provider and per-purpose bindings"
```

---

### Task 15: Admin API — providers, bindings, kinds, purposes

**Files:**
- Modify: `backend/app/features/llm/routers/llm.py` (replace)
- Create: `backend/app/features/llm/schemas/llm_provider.py` (replace)
- Create: `backend/app/features/llm/schemas/llm_binding.py`
- Modify: `backend/app/features/llm/services/admin.py` (replace)
- Delete: `backend/app/features/llm/schemas/llm_route.py`
- Test: `backend/tests/routers/test_llm_admin.py` (update), `backend/tests/services/test_llm_admin.py` (update)

**Interfaces:**
- Produces routes under `/language-model`: `GET /kinds`, `GET /purposes`, CRUD `/providers`, CRUD `/bindings`, `POST /bindings/{purpose}/test`.
- `admin` service: `create_provider/get/update/delete/list`, `create_binding/get/update/delete/list`, `validate_fallback(session, binding_id, fallback_id)` (raises `ApiError(CONFLICT)` on self/cycle).

- [ ] **Step 1: Write the failing tests** — cover: create provider (kind validated against `known_kinds`), `api_key` masked in response, update with masked key keeps stored key, create binding, fallback self → 409, fallback cycle → 409, `GET /kinds` returns `["openai"]`, `GET /purposes` returns the enum, delete provider in use → 409, every mutation calls `invalidate` (spy) and writes audit (assert audit repo row). Reuse the existing router test fixtures/auth.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/routers/test_llm_admin.py tests/services/test_llm_admin.py -v`

- [ ] **Step 3: Implement schemas**

```python
# backend/app/features/llm/schemas/llm_provider.py
from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel


class LLMProviderBase(BaseModel):
    name: str
    provider: str = "openai"
    model: str
    base_url: str | None = None
    api_key: str = ""
    timeout_seconds: float = 60.0
    max_retries: int = 2
    rate_limit_rps: int | None = None
    rate_limit_rpm: int | None = None
    max_queue_size: int = 50
    enabled: bool = True


class LLMProviderCreate(LLMProviderBase):
    pass


class LLMProviderUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float | None = None
    max_retries: int | None = None
    rate_limit_rps: int | None = None
    rate_limit_rpm: int | None = None
    max_queue_size: int | None = None
    enabled: bool | None = None


class LLMProviderResponse(BaseModel):
    id: uuid.UUID
    name: str
    provider: str
    model: str
    base_url: str | None = None
    api_key: str
    timeout_seconds: float
    max_retries: int
    rate_limit_rps: int | None = None
    rate_limit_rpm: int | None = None
    max_queue_size: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class LLMProviderListResponse(BaseModel):
    data: list[LLMProviderResponse]
    total: int
```

```python
# backend/app/features/llm/schemas/llm_binding.py
from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel


class LLMBindingBase(BaseModel):
    purpose: str
    provider_id: uuid.UUID
    model_override: str | None = None
    fallback_binding_id: uuid.UUID | None = None
    timeout_override: float | None = None
    enabled: bool = True


class LLMBindingCreate(LLMBindingBase):
    pass


class LLMBindingUpdate(BaseModel):
    provider_id: uuid.UUID | None = None
    model_override: str | None = None
    fallback_binding_id: uuid.UUID | None = None
    timeout_override: float | None = None
    enabled: bool | None = None


class LLMBindingResponse(BaseModel):
    id: uuid.UUID
    purpose: str
    provider_id: uuid.UUID
    provider_name: str
    model: str
    fallback_binding_id: uuid.UUID | None = None
    timeout_override: float | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class LLMBindingListResponse(BaseModel):
    data: list[LLMBindingResponse]
    total: int


class LLMBindingTestResult(BaseModel):
    ok: bool
    latency_ms: int
    model: str | None = None
    error: str | None = None
```

- [ ] **Step 4: Implement admin service** — mirror the current `admin.py` but for providers + bindings; add:

```python
async def validate_fallback(session, binding_id, fallback_id):
    if fallback_id is None:
        return
    if fallback_id == binding_id:
        raise ApiError(ErrorCode.CONFLICT, "binding cannot fall back to itself", status=409)
    seen = {binding_id}
    node = fallback_id
    depth = 0
    while node is not None and depth < 5:
        if node in seen:
            raise ApiError(ErrorCode.CONFLICT, "fallback chain forms a cycle", status=409)
        seen.add(node)
        b = await llm_repo.get_binding(session, node)
        node = b.fallback_binding_id if b else None
        depth += 1
```

`create_provider` validates `data["provider"] in providers.known_kinds()` → else `ApiError(NOT_FOUND/CONFLICT)`. `delete_provider` guards `provider_has_bindings`.

- [ ] **Step 5: Implement the router** — replace `llm.py`. Keep `prefix="/language-model"`, scopes `llm:read`/`llm:write`, `MASK` for `api_key`, `record_audit` + `invalidate()` on each mutation. Endpoints: `GET /kinds` → `{"data": list(known_kinds())}`; `GET /purposes` → `{"data": list(KNOWN_PURPOSES)}`; providers CRUD; bindings CRUD (create/update call `validate_fallback`); `POST /bindings/{purpose}/test` → `service.ping`. `_binding_response` resolves `provider_name` and effective `model`.

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/routers/test_llm_admin.py tests/services/test_llm_admin.py -v`

- [ ] **Step 7: Commit**

```bash
git add backend/app/features/llm/routers/llm.py backend/app/features/llm/schemas/ backend/app/features/llm/services/admin.py backend/tests/routers/test_llm_admin.py backend/tests/services/test_llm_admin.py
git rm backend/app/features/llm/schemas/llm_route.py
git commit -m "feat(llm): admin API for providers, bindings, kinds, purposes"
```

---

### Task 16: Migrate the five call sites

**Files:**
- Modify: `backend/app/features/chat/services/llm.py` (classification → `parse`)
- Modify: `backend/app/features/agency/services/evaluation.py` (`_judge` → `parse`)
- Modify: `backend/app/features/agency/services/agency.py` (`parse_specification` → `parse`)
- Modify: `backend/app/features/analytics/services/popular_questions.py` (`_ask_llm` → `parse`)
- Modify: `backend/app/features/analytics/services/brief.py` (`chat` signature)
- Test: update each feature's existing service test to the new return types.

**Interfaces:**
- Consumes: `parse`, `chat`, `Purpose`, result schemas (Task 13).

- [ ] **Step 1: Update the failing tests** — for each caller, assert the new behavior with a fake LLM:
  - classification: `classify_message_category` sets the category from `ClassificationResult.category`.
  - judge: `_judge` returns `(score, reason)` from `JudgeResult`.
  - parse_spec: `parse_specification` returns the dict from `SpecResult.model_dump()`.
  - popular_questions: `_ask_llm` returns `list[dict]` from `PopularQuestionsResult`.
  - brief: unchanged output; only the call signature updates.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/ -k "classify or judge or spec or popular or brief" -v`

- [ ] **Step 3: Implement each call site**

```python
# chat/services/llm.py  (inside classify_message_category)
from app.features.llm.services import LlmError, Purpose, parse
try:
    async with AsyncSessionLocal() as session, session.begin():
        result = await parse(session, Purpose.CLASSIFICATION,
                             messages=[{"role": "user", "content": content}])
        await message_repo.set_category(session, message_id, result.category)
except (LlmError, Exception) as e:
    logger.error("Error classifying message category: %s", e)
```

```python
# agency/services/evaluation.py  (_judge)
from app.features.llm.services import Purpose, parse
result = await parse(session, Purpose.JUDGE, messages=[{"role": "user", "content": prompt}])
return float(result.score), str(result.reason)
```

```python
# agency/services/agency.py  (parse_specification, replacing the tools payload)
from app.features.llm.services import Purpose, parse
async with AsyncSessionLocal() as session, session.begin():
    result = await parse(session, Purpose.PARSE_SPEC, messages=payload["messages"])
return result.model_dump()
```

Remove the now-unused `tools`/`tool_choice` inline JSON-schema block in `agency.py` (the `SpecResult` schema replaces it). Keep `payload["messages"]` construction.

```python
# analytics/services/popular_questions.py  (_ask_llm)
from app.features.llm.services import LlmError, Purpose, parse
try:
    result = await parse(session, Purpose.POPULAR_QUESTIONS,
                         messages=[{"role": "user", "content": prompt}])
    return [q.model_dump() for q in result.questions]
except (LlmError, Exception) as e:
    logger.error("popular questions LLM call failed: %s", e)
    return []
```

```python
# analytics/services/brief.py  (_generate_brief_content)
from app.features.llm.services import Purpose, chat
res = await chat(session, Purpose.BRIEF, messages=[{"role": "user", "content": prompt}])
return res.content, "ok"
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/ -k "classify or judge or spec or popular or brief" -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/features/chat/services/llm.py backend/app/features/agency/services/evaluation.py backend/app/features/agency/services/agency.py backend/app/features/analytics/services/popular_questions.py backend/app/features/analytics/services/brief.py backend/tests/
git commit -m "refactor(llm): move call sites to parse()/chat() with typed results"
```

---

### Task 17: Full suite, cleanup, MEMORY

**Files:**
- Modify: `MEMORY.md`
- Delete: any remaining references to `llm_route`, `llm_providers`, `llm_routes`, `client._resolve`.

- [ ] **Step 1: Grep for stragglers**

Run: `grep -rnE "llm_route|llm_providers|llm_routes|services.client|auth_scheme|request_usage" backend/app backend/tests` — expect no hits in live code.

- [ ] **Step 2: Run the whole backend suite**

Run: `uv run pytest -q`
Expected: PASS except the known pre-existing failures recorded in `MEMORY.md` (`test_orm_models`, `test_router_smoke`).

- [ ] **Step 3: Run graphify update**

Run (from repo root): `graphify update .`

- [ ] **Step 4: Update MEMORY.md** — move the LLM entry from "Current Focus" to reflect DONE; note the new module map, tables, and the `LLM_*` env vars; prune the design-phase wording.

- [ ] **Step 5: Commit**

```bash
git add MEMORY.md graphify-out
git commit -m "chore(llm): finalize pluggable LangChain layer; refresh memory and graph"
```

---

## Notes carried from the spec (confirm during implementation)

- Whether the `openai` integration surfaces `cost` in `response_metadata` / usage details; if not, `cost_usd` stays `None`.
- Exact per-call `max_tokens` mechanism (`.bind` vs constructor) for `langchain-openai`.
- The existing `rate_limit_repo.check(...)` signature and `.allowed` attribute (Task 5 `_allow`).
- `with_retry(retry_if_exception_type=())` acceptance of an empty tuple (Task 10 keeps an `(Exception,)` guard).
- Test fixture names (`db_session` async session, `db_engine_sync` migration engine) must match the project's existing `backend/tests/conftest.py`; if they differ, use the real names throughout.
