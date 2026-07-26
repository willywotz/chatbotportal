import uuid

import pytest

from app.models.conversation import Message
from app.services.chat.turn import save_turn


@pytest.mark.usefixtures("db")
async def test_save_turn_persists_agent_steps():
    snapshot = {"steps": [{"name": "discover", "ms": 10}], "agencies": [], "errors": []}
    saved = await save_turn(
        query="q", conversation_id=str(uuid.uuid4()), answer="a", references=[], category=None,
        agency_ids=[], response_time=1, user=None, succeeded=True, agent_steps=snapshot,
    )
    msg = await Message.get(id=saved.assistant_message_id)
    assert msg.agent_steps == snapshot


@pytest.mark.usefixtures("db")
async def test_save_turn_defaults_agent_steps_to_empty_list():
    saved = await save_turn(
        query="q", conversation_id=str(uuid.uuid4()), answer="a", references=[], category=None,
        agency_ids=[], response_time=1, user=None, succeeded=True,
    )
    msg = await Message.get(id=saved.assistant_message_id)
    assert msg.agent_steps == []
