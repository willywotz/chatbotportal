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
    return runnable
