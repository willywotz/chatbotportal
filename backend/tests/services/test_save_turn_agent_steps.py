import uuid

import pytest

from app.features.chat.models.conversation import Message
from app.features.chat.services.turn import save_turn

pytestmark = pytest.mark.asyncio


async def test_save_turn_persists_agent_steps(db_session):
    snapshot = {"steps": [{"name": "discover", "ms": 10}], "agencies": [], "errors": []}
    saved = await save_turn(
        session=db_session,
        query="q", conversation_id=str(uuid.uuid4()), answer="a", references=[], category=None,
        agency_ids=[], response_time=1, user=None, succeeded=True, agent_steps=snapshot,
    )
    msg = await db_session.get(Message, saved.assistant_message_id)
    assert msg.agent_steps == snapshot


async def test_save_turn_defaults_agent_steps_to_empty_list(db_session):
    saved = await save_turn(
        session=db_session,
        query="q", conversation_id=str(uuid.uuid4()), answer="a", references=[], category=None,
        agency_ids=[], response_time=1, user=None, succeeded=True,
    )
    msg = await db_session.get(Message, saved.assistant_message_id)
    assert msg.agent_steps == []
