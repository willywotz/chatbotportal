from opentelemetry import trace

from app.core.db import AsyncSessionLocal
from app.features.chat.models.conversation import Conversation
from app.features.chat.repositories import conversation as conversation_repo
from app.features.chat.repositories import message as message_repo
from app.features.onechat.services import OneChatClient, get_client

tracer = trace.get_tracer(__name__)


async def ensure_session_warmed(
    conversation: Conversation,
    mcp_endpoint_url: str,
    *,
    client: OneChatClient | None = None,
) -> None:
    """Warm the upstream session for a conversation's first message.

    Opens its own short-lived sessions per DB touch (same pattern as
    app.features.chat.services.stream): `conversation` was loaded in the caller's own
    (now closed) session, so the save below re-attaches it via `session.merge`.
    """
    with tracer.start_as_current_span("chat_stream_endpoint") as span:
        if conversation.external_session_id is not None:
            span.set_attribute("session_already_warmed", True)
            return

        async with AsyncSessionLocal() as session, session.begin():
            first_msg = await message_repo.first_user_message(session, conversation.id)
        if first_msg is None:
            span.set_attribute("no_first_message", True)
            return

        span.set_attribute("warming_session_for_conversation", str(conversation.id))
        span.set_attribute("query", first_msg.content)

        try:
            oc = client or get_client()
            body = await oc.chat_v3(first_msg.content, mcp_endpoint_url, str(conversation.id))
            data = body.get("data", {})
            conversation.external_session_id = data.get("session_id") or str(conversation.id)
            span.set_attribute("warmed_session_id", conversation.external_session_id)
        except Exception as e:
            span.set_status(trace.StatusCode.ERROR, f"Session warm-up failed: {str(e)}")
            span.set_attributes({"error": "Session warm-up failed", "exception": str(e)})
            raise e

        try:
            async with AsyncSessionLocal() as session, session.begin():
                merged = await session.merge(conversation)
                await conversation_repo.save(session, merged, update_fields=["external_session_id"])
        except Exception as e:
            span.set_status(trace.StatusCode.ERROR, f"Failed to save warmed session: {str(e)}")
            span.set_attributes({"error": "Failed to save warmed session", "exception": str(e)})
            raise e
