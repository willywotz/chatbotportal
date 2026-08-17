from app.models.conversation import Conversation, Message
from app.models.user import User
from app.services.openai import conversations as conversation_service
from app.services.responses.errors import ResponsesApiError


async def test_create_conversation_persists_metadata_and_owner(db):
    u = await User.create(email="a@x.com", hashed_password="h")
    conv = await conversation_service.create_conversation({"k": "v"}, u.id)
    assert conv.metadata == {"k": "v"} and conv.user_id == u.id


async def test_persist_items_bulk_creates_messages(db):
    conv = await Conversation.create(title="t")

    class Item:
        def __init__(self, role, content):
            self.role, self.content = role, content

    rows = await conversation_service.persist_items(
        [Item("user", "hi"), Item("assistant", "yo")], conv.id, None
    )
    assert len(rows) == 2
    assert await Message.filter(conversation_id=conv.id).count() == 2


async def test_load_conversation_not_found_raises(db):
    u = await User.create(email="b@x.com", hashed_password="h")
    try:
        await conversation_service.load_conversation("conv_bad-uuid", u)
        assert False, "expected ResponsesApiError"
    except ResponsesApiError as e:
        assert e.param == "conversation_id" and e.code == "conversation_not_found"


async def test_load_conversation_returns_owned_row(db):
    u = await User.create(email="c@x.com", hashed_password="h")
    conv = await Conversation.create(title="t", user_id=u.id)
    loaded = await conversation_service.load_conversation(f"conv_{conv.id}", u)
    assert loaded.id == conv.id


async def test_update_metadata_saves(db):
    conv = await Conversation.create(title="t", metadata={"a": "1"})
    await conversation_service.update_metadata(conv, {"b": "2"})
    fresh = await Conversation.get(id=conv.id)
    assert fresh.metadata == {"b": "2"}


async def test_soft_delete_conversation_marks_conv_and_messages(db):
    conv = await Conversation.create(title="t")
    await Message.create(conversation_id=conv.id, role="user", content="hi")
    await conversation_service.soft_delete_conversation(conv)
    assert conv.deleted_at is not None
    msg = await Message.filter(conversation_id=conv.id).first()
    assert msg.deleted_at is not None


async def test_load_item_not_found_raises(db):
    conv = await Conversation.create(title="t")
    try:
        await conversation_service.load_item(conv, "msg_bad-uuid")
        assert False, "expected ResponsesApiError"
    except ResponsesApiError as e:
        assert e.param == "item_id" and e.code == "item_not_found"


async def test_create_items_returns_fresh_rows(db):
    conv = await Conversation.create(title="t")

    class Item:
        def __init__(self, role, content):
            self.role, self.content = role, content

    rows = await conversation_service.create_items(conv, [Item("user", "hi")])
    assert len(rows) == 1 and rows[0].content == "hi"


async def test_list_items_orders_and_reports_has_more(db):
    conv = await Conversation.create(title="t")
    for i in range(3):
        await Message.create(conversation_id=conv.id, role="user", content=str(i))

    rows, has_more = await conversation_service.list_items(
        conv, limit=2, order="asc", after_cursor=None
    )
    assert len(rows) == 2 and has_more is True
    assert [r.content for r in rows] == ["0", "1"]


async def test_delete_item_marks_deleted(db):
    conv = await Conversation.create(title="t")
    msg = await Message.create(conversation_id=conv.id, role="user", content="hi")
    await conversation_service.delete_item(msg)
    fresh = await Message.get(id=msg.id)
    assert fresh.deleted_at is not None
