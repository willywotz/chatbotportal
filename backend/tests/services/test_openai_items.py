from app.models.conversation import Conversation, Message
from app.services.openai.items import flatten_content, item_from_message, list_envelope


def test_flatten_content_variants():
    assert flatten_content("hi") == "hi"
    assert flatten_content([{"text": "a"}, {"text": "b"}]) == "a b"
    assert flatten_content(None) == ""


async def test_item_from_message_uses_input_text_for_user(db):
    c = await Conversation.create(title="t")
    m = await Message.create(conversation_id=c.id, role="user", content="q")
    item = item_from_message(m)
    assert item["id"] == f"msg_{m.id}"
    assert item["content"][0] == {"type": "input_text", "text": "q"}


async def test_item_from_message_uses_output_text_for_assistant(db):
    c = await Conversation.create(title="t")
    m = await Message.create(conversation_id=c.id, role="assistant", content="a")
    assert item_from_message(m)["content"][0]["type"] == "output_text"


def test_list_envelope_empty():
    assert list_envelope([]) == {"object": "list", "data": [],
                                  "first_id": None, "last_id": None, "has_more": False}


def test_list_envelope_bounds_and_has_more():
    env = list_envelope([{"id": "msg_1"}, {"id": "msg_2"}], has_more=True)
    assert env["first_id"] == "msg_1" and env["last_id"] == "msg_2" and env["has_more"] is True
