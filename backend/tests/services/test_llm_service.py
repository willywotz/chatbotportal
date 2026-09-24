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
    if "boomsvc" not in providers.known_kinds():
        providers.register(ProviderSpec(kind="boomsvc", model_provider="openai",
                                        transient_errors=(RuntimeError,),
                                        map_error=lambda e: None, build_model=boom_model))
    rate_limit.reset_cache()
    await make_binding("brief", kind="boomsvc")
    with pytest.raises(LlmError):
        await service.chat(db_session, Purpose.BRIEF, [{"role": "user", "content": "x"}])
    assert recorded.get("called") is True
