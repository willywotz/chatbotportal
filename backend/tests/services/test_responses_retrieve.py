import pytest
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.responses.errors import ResponsesApiError
from app.services.responses.retrieve import (
    input_items, load_assistant_message, response_object,
)


async def test_response_object_reconstructs_portal_block(db):
    u = await User.create(email="o@x.y", hashed_password="!")
    c = await Conversation.create(title="t", user_id=u.id)
    await Message.create(conversation_id=c.id, role="user", content="q", user_id=u.id)
    a = await Message.create(conversation_id=c.id, role="assistant", content=" ans ",
                             summary="สรุป", agency_ids=["a-1"], user_id=u.id)
    msg = await load_assistant_message(f"resp_{a.id}", u)
    body = response_object(msg)
    assert body["id"] == f"resp_{a.id}" and body["status"] == "completed"
    assert body["output_text"] == "ans" and body["portal"]["stream_version"] == "v5"
    items = await input_items(msg, order="desc", limit=20)
    assert items["data"][0]["content"][0]["text"] == "q"


async def test_foreign_owner_is_not_found(db):
    owner = await User.create(email="p@x.y", hashed_password="!")
    other = await User.create(email="q@x.y", hashed_password="!")
    c = await Conversation.create(title="t", user_id=owner.id)
    a = await Message.create(conversation_id=c.id, role="assistant", content="x", user_id=owner.id)
    with pytest.raises(ResponsesApiError) as e:
        await load_assistant_message(f"resp_{a.id}", other)
    assert e.value.status == 404 and e.value.code == "response_not_found"


async def test_malformed_id_is_not_found(db):
    with pytest.raises(ResponsesApiError) as e:
        await load_assistant_message("resp_not-a-uuid", None)
    assert e.value.code == "response_not_found"
