import httpx

from app.models.conversation import Conversation, Message
from app.services.onechat import OneChatClient
from app.services.session import ensure_session_warmed


async def test_warm_up_uses_chat_v3_and_stores_session_id(db):
    conv = await Conversation.create(title="t")
    await Message.create(conversation_id=conv.id, role="user", content="hello")

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": {"session_id": "ext-1"}})

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await ensure_session_warmed(conv, "http://mcp", client=client)

    assert seen["url"] == "http://oc:8000/v3/chat"
    refreshed = await Conversation.get(id=conv.id)
    assert refreshed.external_session_id == "ext-1"


async def test_warm_up_noop_when_no_first_message(db):
    conv = await Conversation.create(title="t")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await ensure_session_warmed(conv, "http://mcp", client=client)

    refreshed = await Conversation.get(id=conv.id)
    assert refreshed.external_session_id is None


async def test_warm_up_falls_back_to_conversation_id_when_no_session_in_response(db):
    conv = await Conversation.create(title="t")
    await Message.create(conversation_id=conv.id, role="user", content="hello")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {}})

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await ensure_session_warmed(conv, "http://mcp", client=client)

    refreshed = await Conversation.get(id=conv.id)
    assert refreshed.external_session_id == str(conv.id)


async def test_warm_up_noop_when_already_warmed(db):
    conv = await Conversation.create(title="t", external_session_id="already")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    client = OneChatClient("http://oc:8000", transport=httpx.MockTransport(handler))
    await ensure_session_warmed(conv, "http://mcp", client=client)
