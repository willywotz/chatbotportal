"""Characterization tests for the similarity join refactor (Task 12).

These tests pin the behavior of find_similar_question using a live SQLite db
fixture so that the post-match 3-query tail → single-join refactor can be
verified to produce identical results.
"""

import pytest

from app.models.connection_log import ConnectionLog
from app.models.conversation import Conversation, Message


async def _build_cache_entry(
    question: str = "how to renew passport",
    answer: str = "visit the embassy",
    conv_status: str = "success",
) -> tuple[Message, Message, ConnectionLog, Conversation]:
    conv = await Conversation.create(status=conv_status)
    user_msg = await Message.create(
        conversation=conv,
        role="user",
        content=question,
    )
    asst_msg = await Message.create(
        parent_id=user_msg.id,
        conversation=conv,
        role="assistant",
        content=answer,
        sources=[{"title": "source1"}],
        agent_steps=[{"step": "looked it up"}],
        agency_ids=["agency-1"],
    )
    cl = await ConnectionLog.create(
        connection_type="API",
        status="success",
        action="query",
        assistant_message_id=asst_msg.id,
        response_body='{"answer": "visit the embassy"}',
    )
    return user_msg, asst_msg, cl, conv


@pytest.mark.usefixtures("db")
async def test_match_resolution_returns_correct_objects():
    from unittest.mock import AsyncMock, patch

    from app.services import similarity

    user_msg, asst_msg, cl, conv = await _build_cache_entry()

    with patch.object(
        similarity, "effective_cutoff", new=AsyncMock(return_value=None)
    ), patch.object(
        similarity, "_similarity_search", new=AsyncMock(return_value=user_msg)
    ):
        result = await similarity.find_similar_question("how to renew passport")

    assert result is not None
    got_user, got_asst, got_cl = result
    assert got_user.id == user_msg.id
    assert got_asst.id == asst_msg.id
    assert got_cl.id == cl.id


@pytest.mark.usefixtures("db")
async def test_match_resolution_preserves_payload_fields():
    from unittest.mock import AsyncMock, patch

    from app.services import similarity

    user_msg, asst_msg, cl, _ = await _build_cache_entry()

    with patch.object(
        similarity, "effective_cutoff", new=AsyncMock(return_value=None)
    ), patch.object(
        similarity, "_similarity_search", new=AsyncMock(return_value=user_msg)
    ):
        result = await similarity.find_similar_question("how to renew passport")

    assert result is not None
    _, got_asst, got_cl = result
    assert got_asst.content == "visit the embassy"
    assert got_asst.sources == [{"title": "source1"}]
    assert got_asst.agent_steps == [{"step": "looked it up"}]
    assert got_asst.agency_ids == ["agency-1"]
    assert got_cl.response_body == '{"answer": "visit the embassy"}'


@pytest.mark.usefixtures("db")
async def test_non_success_conversation_excluded():
    from unittest.mock import AsyncMock, patch

    from app.services import similarity

    user_msg, _, _, _ = await _build_cache_entry(conv_status="failed")

    with patch.object(
        similarity, "effective_cutoff", new=AsyncMock(return_value=None)
    ), patch.object(
        similarity, "_similarity_search", new=AsyncMock(return_value=user_msg)
    ):
        result = await similarity.find_similar_question("how to renew passport")

    assert result is None


@pytest.mark.usefixtures("db")
async def test_no_match_returns_none():
    from unittest.mock import AsyncMock, patch

    from app.services import similarity

    with patch.object(
        similarity, "effective_cutoff", new=AsyncMock(return_value=None)
    ), patch.object(
        similarity, "_similarity_search", new=AsyncMock(return_value=None)
    ):
        result = await similarity.find_similar_question("completely unique question")

    assert result is None


@pytest.mark.usefixtures("db")
async def test_missing_assistant_message_returns_none():
    from unittest.mock import AsyncMock, patch

    from app.services import similarity

    conv = await Conversation.create(status="success")
    user_msg = await Message.create(
        conversation=conv, role="user", content="orphan question"
    )

    with patch.object(
        similarity, "effective_cutoff", new=AsyncMock(return_value=None)
    ), patch.object(
        similarity, "_similarity_search", new=AsyncMock(return_value=user_msg)
    ):
        result = await similarity.find_similar_question("orphan question")

    assert result is None


@pytest.mark.usefixtures("db")
async def test_missing_conn_log_returns_none():
    from unittest.mock import AsyncMock, patch

    from app.services import similarity

    conv = await Conversation.create(status="success")
    user_msg = await Message.create(
        conversation=conv, role="user", content="no-log question"
    )
    await Message.create(
        parent_id=user_msg.id,
        conversation=conv,
        role="assistant",
        content="answer without log",
    )

    with patch.object(
        similarity, "effective_cutoff", new=AsyncMock(return_value=None)
    ), patch.object(
        similarity, "_similarity_search", new=AsyncMock(return_value=user_msg)
    ):
        result = await similarity.find_similar_question("no-log question")

    assert result is None


@pytest.mark.usefixtures("db")
async def test_query_count_tail_is_one_raw_join(monkeypatch):
    from unittest.mock import AsyncMock, patch

    from tortoise import Tortoise

    from app.services import similarity

    user_msg, _, _, _ = await _build_cache_entry()

    calls: dict[str, int] = {"n": 0}
    real_get_connection = Tortoise.get_connection

    def patched_get_connection(name: str):
        conn = real_get_connection(name)
        orig = conn.__class__.execute_query_dict

        async def counting(self, *a, **k):
            calls["n"] += 1
            return await orig(self, *a, **k)

        monkeypatch.setattr(conn.__class__, "execute_query_dict", counting)
        monkeypatch.setattr(Tortoise, "get_connection", real_get_connection)
        return conn

    monkeypatch.setattr(Tortoise, "get_connection", patched_get_connection)

    with patch.object(
        similarity, "effective_cutoff", new=AsyncMock(return_value=None)
    ), patch.object(
        similarity, "_similarity_search", new=AsyncMock(return_value=user_msg)
    ):
        result = await similarity.find_similar_question("how to renew passport")

    assert result is not None
    # The counter wraps execute_query_dict on the raw connection object returned by
    # Tortoise.get_connection; ORM Model.get() calls use the pool directly and are
    # not counted here.  The single raw SQL call is the join query that resolves
    # asst_id + cl_id and verifies conversation status in one round-trip.
    assert calls["n"] == 1
