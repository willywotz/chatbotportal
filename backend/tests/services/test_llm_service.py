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
async def test_ping_ok_for_structured_purpose(db_session, fake_openai, make_binding):
    await make_binding("classification", kind="fk")
    result = await service.ping(db_session, Purpose.CLASSIFICATION)
    assert result.ok is True


@pytest.mark.asyncio
async def test_usage_recorded_when_parse_fails_after_call(db_session, make_binding, monkeypatch):
    from langchain_core.exceptions import OutputParserException
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.runnables import RunnableLambda

    class _UsageThenParseFail(BaseChatModel):
        @property
        def _llm_type(self):
            return "usage-then-parse-fail"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            msg = AIMessage(content="x",
                            usage_metadata={"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
                            response_metadata={"model_name": "fakemodel"})
            return ChatResult(generations=[ChatGeneration(message=msg)],
                              llm_output={"model_name": "fakemodel"})

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            return self._generate(messages, stop, run_manager, **kwargs)

        def with_structured_output(self, schema, **kwargs):
            def _boom(_value):
                raise OutputParserException("cannot parse")
            return self | RunnableLambda(_boom)

    recorded = {}

    async def spy_record(session, metadata, **kw):
        recorded["metadata"] = metadata
    monkeypatch.setattr(service.usage, "record", spy_record)

    if "usageemit" not in providers.known_kinds():
        providers.register(ProviderSpec(kind="usageemit", model_provider="openai",
                                        transient_errors=(ValueError,),
                                        map_error=lambda e: None,
                                        build_model=lambda model, **kw: _UsageThenParseFail()))
    rate_limit.reset_cache()
    await make_binding("classification", kind="usageemit")

    with pytest.raises(LlmError) as e:
        await service.parse(db_session, Purpose.CLASSIFICATION,
                            [{"role": "user", "content": "x"}])
    assert e.value.kind == "parse"
    assert recorded["metadata"], "usage must be recorded even when the parser fails after the call"


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
