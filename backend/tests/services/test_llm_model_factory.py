import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from app.features.llm.services import providers, model_factory, rate_limit
from app.features.llm.services.providers import ProviderSpec
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
                max_queue_size=10, headers={})
    base.update(kw)
    return ResolvedRoute(**base)


@pytest.mark.asyncio
async def test_build_invokes(fake_kind):
    runnable = model_factory.build(_route())
    out = await runnable.ainvoke([{"role": "user", "content": "hey"}])
    assert isinstance(out, AIMessage)


@pytest.mark.asyncio
async def test_build_passes_custom_headers(fake_kind):
    captured = {}

    def build_model(model, **kwargs):
        captured.update(kwargs)
        return GenericFakeChatModel(messages=iter([AIMessage(content="hi")]))
    providers.register(ProviderSpec(kind="hdrspec", model_provider="openai",
                                    transient_errors=(), map_error=lambda e: None,
                                    build_model=build_model))
    model_factory.build(_route(kind="hdrspec", headers={"X-Title": "portal"}))
    assert captured["default_headers"] == {"X-Title": "portal"}
