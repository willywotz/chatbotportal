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
            try:
                out = await runnable.ainvoke(messages)
            finally:
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
        out = await chat(session, purpose, [{"role": "user", "content": "ping"}], max_tokens=1)
        model = getattr(out, "response_metadata", {}).get("model_name")
        return LlmPingResult(ok=True, latency_ms=_ms(start), model=model, error=None)
    except LlmError as exc:
        return LlmPingResult(ok=False, latency_ms=_ms(start), model=None, error=str(exc))


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)
