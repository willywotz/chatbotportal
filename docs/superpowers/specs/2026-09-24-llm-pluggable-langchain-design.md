# LLM Management — Unified, Pluggable Layer on LangChain

- Date: 2026-09-24
- Branch: `feat/llm-pluggable-langchain`
- Status: design approved; awaiting spec review before planning
- Scope: `backend/app/features/llm/`

## 1. Goal

Make the internal LLM call layer unified and pluggable, on the LangChain
standard interfaces. One public entry point stays stable for callers. Behind
it, the provider protocol, transport, tool-calling, structured output,
retries, and fallbacks are LangChain's job. Adding a new provider later is
one package install plus one registry line — no change to callers.

This is greenfield. The old hand-rolled `httpx` client and its data shapes
are replaced, not preserved.

### In scope

- LangChain as the unified layer (`init_chat_model`, Runnable composition).
- Structured output for structured purposes (`with_structured_output`).
- Provider-agnostic token accounting (`get_usage_metadata_callback`).
- Retries on transient errors (`.with_retry`).
- Route-level fallbacks (`.with_fallbacks`).
- Distributed rate limiting as a `BaseRateLimiter` (Redis).
- Reshaped data model, migration, and admin API.

### Out of scope

- Streaming chat turns. These go through OneChat
  (`app/features/chat/services/stream.py`), not this layer.
- Embeddings, vector stores, and other LangChain features.
- A UI. The admin API is in scope; the front end is not.

### Non-goals / constraints

- The public `service` interface must not leak LangChain types outward beyond
  `AIMessage` (freeform) and the purpose result schemas (structured).
- LangChain stays inside this infrastructure layer only (clean architecture).
- 15-factor: config from env where it is a deployment concern; secrets never
  logged.
- TDD is mandatory. No network in tests.

## 2. Only one provider ships now

`openai` (OpenAI-compatible) is the only provider kind shipped. The seam is
proven by structure, not by a second protocol. `base_url` lets one `openai`
kind serve OpenAI, OpenRouter, vLLM, Ollama's OpenAI endpoint, and gateways.

Plug a new provider later: `pip install langchain-<provider>`, add one
`ProviderSpec` line. Plug a new structured purpose: add the enum value and a
result schema. Neither touches `service.py`.

## 3. Component and file layout

```
backend/app/features/llm/services/
  service.py         # PUBLIC API: chat() (freeform) + parse() (structured)
  resolve.py         # binding+provider (+fallback chain) from DB -> ResolvedRoute; 30s cache
  model_factory.py   # assemble the LangChain runnable for a ResolvedRoute
  providers.py       # the plug: kind -> model_provider, transient_errors, map_error, build_model
  rate_limit.py      # RedisRateLimiter(BaseRateLimiter): distributed token bucket + queue-full
  purpose.py         # Purpose enum + PURPOSE_SCHEMAS
  result_schemas.py  # Pydantic output schemas
  errors.py          # LlmError + to_llm_error(exc, spec)
  usage.py           # record token usage from the callback
  __init__.py        # public exports
```

Responsibilities:

| Module | Owns |
|---|---|
| `service.py` | The two entry points. Each opens `get_usage_metadata_callback()`, runs the runnable, records usage in a `finally`, and maps errors. Returns an `AIMessage` (`chat`) or a validated Pydantic object (`parse`). |
| `resolve.py` | DB lookup of the enabled binding + provider and its fallback chain; 30s cache; `invalidate()`. |
| `model_factory.py` | Build the runnable: `init_chat_model(..., rate_limiter=)` -> `bind_tools`/`with_structured_output` -> `.with_retry` -> `.with_fallbacks`. |
| `providers.py` | `kind -> ProviderSpec` registry; `known_kinds()`. `openai` ships now. |
| `rate_limit.py` | `RedisRateLimiter` over the existing Redis counters, with per-provider RPS/RPM and queue-full fast-fail. |
| `purpose.py` / `result_schemas.py` | Each purpose maps to an optional structured-output schema. |
| `errors.py` | `LlmError` and central exception mapping. |
| `usage.py` | Persist one `llm_usage` row from the callback aggregate. |

## 4. Data model

Fresh shapes. Migration `0006` creates them; the old columns are irrelevant.

### `llm_provider`

| Column | Type | Note |
|---|---|---|
| `id` | uuid PK | |
| `name` | str, unique | human label |
| `provider` | str | LangChain `model_provider`; validated against `known_kinds()` |
| `model` | str | default model id |
| `base_url` | str, null | OpenAI-compatible / self-hosted endpoints |
| `api_key` | text | secret; masked in every response |
| `timeout_seconds` | float | `init_chat_model(timeout=)` |
| `max_retries` | int | `.with_retry(stop_after_attempt = max_retries + 1)` |
| `rate_limit_rps` | int, null | `RedisRateLimiter` |
| `rate_limit_rpm` | int, null | `RedisRateLimiter` |
| `max_queue_size` | int | `RedisRateLimiter` |
| `enabled` | bool | |
| `created_at` / `updated_at` | ts | |

### `llm_binding`

| Column | Type | Note |
|---|---|---|
| `id` | uuid PK | |
| `purpose` | str, unique | one binding per purpose |
| `provider_id` | uuid FK -> `llm_provider` | `ondelete RESTRICT` |
| `model_override` | str, null | else provider's `model` |
| `fallback_binding_id` | uuid FK -> `llm_binding`, null | `ondelete SET NULL`; drives `.with_fallbacks` |
| `timeout_override` | float, null | |
| `enabled` | bool | |
| `created_at` / `updated_at` | ts | |

### `llm_usage`

Per-call accounting, populated by the usage callback: `model`, `purpose`,
`prompt_tokens`, `completion_tokens`, `cost_usd` (nullable), `user_id`,
`agency_id`, `conversation_id`, `api_key_id`, `created_at`. `total_tokens` is
a derived property.

### Migration `0006_llm_pluggable_langchain`

- Create `llm_provider`, `llm_binding`, `llm_usage` in the shapes above.
- Downgrade drops the three tables.

## 5. Public service API

`service.py` is the only module callers import.

```python
async def chat(session, purpose, messages, *, tools=None, tool_choice=None,
               max_tokens=None, user_id=None, agency_id=None,
               conversation_id=None) -> AIMessage:
    """Freeform turn. Returns the AIMessage (content, tool_calls)."""

async def parse(session, purpose, messages, *, schema=None, max_tokens=None,
                user_id=None, agency_id=None,
                conversation_id=None) -> BaseModel:
    """Structured turn. schema defaults to PURPOSE_SCHEMAS[purpose];
    returns a validated instance."""
```

`session` is the `AsyncSession` (first positional, matching the codebase
convention). `service.py` fetches `spec = providers.get(resolved.kind)` for
error mapping.

Shared internal flow:

```
1. resolved = await resolve.for_purpose(session, purpose)   # + fallback chain
2. runnable = model_factory.build(resolved, schema=?, tools=?, tool_choice=?)
3. if max_tokens: runnable = runnable.bind(max_tokens=max_tokens)
4. try:
       with get_usage_metadata_callback() as cb:
           out = await runnable.ainvoke(messages)
   except Exception as exc:
       raise errors.to_llm_error(exc, spec)
   finally:
       await usage.record(session, cb.usage_metadata, purpose=purpose, ...owner ids)
5. return out
```

Rules:

- `schema` and `tools` are mutually exclusive per call (both drive
  tool-calling). `service.py` rejects the combination before any call.
- `messages` is a list of OpenAI-style `{"role","content"}` dicts, passed
  straight to `ainvoke` (LangChain accepts this; no conversion layer).
- `max_tokens` per call uses `.bind(max_tokens=...)` so the cached base
  runnable stays reusable; `ping` caps at 1.

### `purpose.py`

```python
class Purpose(StrEnum):
    CLASSIFICATION = "classification"
    BRIEF = "brief"
    JUDGE = "judge"
    PARSE_SPEC = "parse_spec"
    POPULAR_QUESTIONS = "popular_questions"

PURPOSE_SCHEMAS: dict[Purpose, type[BaseModel] | None] = {
    Purpose.CLASSIFICATION: ClassificationResult,
    Purpose.JUDGE: JudgeResult,
    Purpose.PARSE_SPEC: SpecResult,
    Purpose.POPULAR_QUESTIONS: PopularQuestionsResult,
    Purpose.BRIEF: None,
}
```

### `result_schemas.py`

Pydantic models with docstrings and field descriptions (the documented best
practice, so the model fills them reliably). Example:

```python
class ClassificationResult(BaseModel):
    """Category of a Thai government-service question."""
    category: Literal[
        "สอบถามข้อมูล", "ตรวจสอบสถานะ", "ขั้นตอนดำเนินการ",
        "กฎหมาย/ระเบียบ", "ไม่สามารถจัดหมวดหมู่ได้",
    ] = Field(description="The single best-fit category.")
```

`JudgeResult`, `SpecResult`, and `PopularQuestionsResult` are defined during
implementation from the current call sites' needs.

## 6. resolve, rate_limit, model_factory

### `resolve.py`

```python
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

async def for_purpose(session, purpose) -> ResolvedRoute: ...  # cached 30s
def invalidate() -> None: ...
```

`for_purpose` loads the enabled binding, checks the provider is enabled,
applies `model_override`, then follows `fallback_binding_id` to build the
chain (depth <= 3, cycle-guarded, disabled links skipped). No enabled
binding or disabled provider -> `LlmError(kind="config")`.

### `rate_limit.py`

```python
class RedisRateLimiter(BaseRateLimiter):     # one instance per provider, cached by name
    async def aacquire(self, *, blocking: bool = True) -> bool:
        # per-provider RPS then RPM window over the existing Redis counters;
        # queue-full -> raise LlmError(kind="queue_full")  (fast-fail, not block)
```

The limiter is passed into the model, so LangChain calls `aacquire` before
each attempt. `InMemoryRateLimiter` is single-process only and cannot limit
across instances, so a Redis `BaseRateLimiter` is the correct fit for a
horizontally-scaled service. Queue-full fast-fail is our behavior inside
`aacquire`; the base limiter only smooths.

### `model_factory.py`

```python
def build(resolved, *, schema=None, tools=None, tool_choice=None) -> Runnable:
    spec = providers.get(resolved.kind)
    model = spec.build_model(                       # defaults to init_chat_model
        resolved.model, model_provider=spec.model_provider,
        api_key=resolved.api_key, base_url=resolved.base_url,
        timeout=resolved.timeout,
        max_retries=0,                              # off; we drive retry below
        rate_limiter=rate_limit.limiter_for(resolved),
    )
    if tools:   model = model.bind_tools(tools, tool_choice=tool_choice)
    if schema:  model = model.with_structured_output(schema)
    runnable = model.with_retry(
        retry_if_exception_type=spec.transient_errors,
        stop_after_attempt=resolved.max_retries + 1,
        wait_exponential_jitter=True,
    )
    if resolved.fallback:
        runnable = runnable.with_fallbacks(
            [build(resolved.fallback, schema=schema, tools=tools,
                   tool_choice=tool_choice)])
    return runnable
```

Rationale:

- Tools/structured wrap the base model first, so every retry and every
  fallback returns the same shape.
- `.with_retry` on the single model, then `.with_fallbacks` switches
  provider — retry only the runnable that fails, not the whole chain.
- `max_retries=0` in the constructor so LangChain's built-in retry does not
  double with `.with_retry`.
- Base `BaseChatModel` and `RedisRateLimiter` are cached per provider
  (invalidated by `resolve.invalidate()` + 30s TTL); the per-call composition
  is cheap and done each call.

### `providers.py`

```python
@dataclass(frozen=True)
class ProviderSpec:
    kind: str
    model_provider: str
    transient_errors: tuple[type[Exception], ...]
    map_error: Callable[[Exception], LlmError | None]
    build_model: Callable[..., BaseChatModel] = init_chat_model

def register(spec) -> None: ...        # raises on duplicate kind
def get(kind) -> ProviderSpec: ...     # unknown -> LlmError(kind="config")
def known_kinds() -> tuple[str, ...]: ...
```

`openai` registers a spec whose `transient_errors` and `map_error` cover the
`openai` SDK's timeout / rate-limit / 5xx / connection errors. `build_model`
is the test seam: a test registers a spec that returns a LangChain fake.

## 7. Error handling

Callers see only `LlmError`. `service.py` maps every raw exception through
`errors.to_llm_error(exc, spec)`.

```python
class LlmError(Exception):
    def __init__(self, message, *, kind, status=None, provider=None): ...
```

| kind | Cause |
|---|---|
| `config` | no enabled binding, provider disabled, unknown `kind` |
| `queue_full` | `RedisRateLimiter` queue cap hit |
| `rate_limited` | provider 429 after retries |
| `timeout` | request timeout after retries |
| `provider` | provider API error (4xx/5xx); carries `status` |
| `network` | connection/transport failure |
| `parse` | structured output failed schema validation |
| `unknown` | anything unmapped |

`to_llm_error` order:

```
1. isinstance(exc, LlmError)                        -> return as-is
2. spec.map_error(exc)                              -> provider-SDK errors
3. OutputParserException | pydantic.ValidationError -> parse
4. httpx.TimeoutException / TransportError          -> timeout / network
5. else                                             -> unknown
```

`.with_retry` handles transient kinds first; only after retries and fallbacks
are exhausted does an exception reach the mapper. `RunnableWithFallbacks`
re-raises the last failure. Usage is recorded in a `finally`, so a call that
consumed tokens then failed still books them; `usage.record` swallows its own
errors and never masks the `LlmError`.

## 8. Consumer changes

`app/features/chat/services/llm.py::classify_message_category` moves from
`chat(...)` + string handling to:

```python
result = await parse(session, Purpose.CLASSIFICATION, messages=[...])
await message_repo.set_category(session, message_id, result.category)
```

Its error branch still logs and does not raise.

## 9. Admin API `/language-model`

- `GET /kinds` -> `{"data": known_kinds()}`.
- `GET /purposes` -> the purpose enum values.
- CRUD `/providers` and `/bindings`.
- Binding create/update validates `fallback_binding_id`: exists, not self, no
  cycle (chain <= 3) -> `ApiError(CONFLICT)` otherwise.
- `POST /bindings/{purpose}/test` -> live ping (a minimal `chat`/`parse` with
  `max_tokens=1`).
- `api_key` masked in every response; a missing/masked key on update keeps the
  stored key.
- Every mutation writes an audit record and calls `resolve.invalidate()`.

Scopes stay `llm:read` / `llm:write`.

## 10. Dependencies

Add to `backend/pyproject.toml`: `langchain`, `langchain-core`,
`langchain-openai`. `langchain-core` >= 0.3.49 (for
`get_usage_metadata_callback`).

Optional, env-gated only (no code): LangSmith tracing via
`LANGSMITH_TRACING` / `LANGSMITH_API_KEY`.

## 11. Testing strategy (TDD)

No network. The `providers.ProviderSpec.build_model` seam lets a test register
a spec whose `build_model` returns a LangChain fake (`GenericFakeChatModel`
for `chat`; a stub runnable returning the Pydantic instance for `parse`).

Unit:

| Module | Cases |
|---|---|
| `providers` | register/get/`known_kinds`; duplicate raises; unknown -> `config`. |
| `resolve` | resolved route + fallback chain; disabled links skipped; cycle and depth-3 guard; disabled provider / no binding -> `config`; 30s cache + `invalidate()`. |
| `rate_limit` | `aacquire` permits within RPS then RPM; queue at cap -> `queue_full`. |
| `model_factory` | assembly order (structured/tools -> retry -> fallbacks); `max_retries=0` on base; `rate_limiter` attached. |
| `errors.to_llm_error` | table-driven: each exception -> expected kind. |

Behavior (`service.py`):

- `chat()` returns the `AIMessage`; `parse()` returns a validated schema;
  absent schema -> clear error.
- Usage recorded (one row, right tokens/purpose/owner ids), including when the
  call then fails.
- `max_tokens` applied via `.bind`; `ping` caps at 1.
- Retry: transient then success within `stop_after_attempt`; exhausted ->
  mapped `LlmError`.
- Fallback: primary raises transient, fallback succeeds -> result from the
  fallback; usage attributed to the fallback model.
- `schema` + `tools` together -> rejected before any call.

Integration (admin API, existing fixtures):

- CRUD `/providers` and `/bindings`; `GET /kinds`; `GET /purposes`;
  `POST /bindings/{purpose}/test`.
- Fallback self/cycle -> `409`.
- `api_key` masked; each mutation audits and calls `resolve.invalidate()`.

Consumer: `classify_message_category` sets the category from
`result.category`; error branch logs and does not raise.

Migration `0006`: upgrade then downgrade smoke test (create/drop three
tables).

## 12. Open items to confirm during implementation

- Whether the `openai` integration surfaces `cost` in `response_metadata`; if
  not, `cost_usd` stays `None` for `parse()` and best-effort for `chat()`.
- Exact per-call `max_tokens` mechanism (`.bind` vs constructor) against
  `langchain-openai`.
- `BaseRateLimiter.aacquire` blocking semantics when raising for queue-full.
