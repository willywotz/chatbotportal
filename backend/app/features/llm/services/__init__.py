from sqlalchemy.ext.asyncio import AsyncSession

from app.features.llm.services import client, usage
from app.features.llm.services.client import (
    KNOWN_PURPOSES, LlmError, LlmPingResult, LlmResult, LlmUsageInfo, invalidate, ping,
)
from app.features.llm.services.purpose import Purpose


async def chat(session: AsyncSession, *, purpose: Purpose, messages: list[dict], tools: list | None = None,
               tool_choice=None, max_tokens: int | None = None,
               user_id=None, agency_id=None, conversation_id=None) -> LlmResult:
    """Public LLM entry point: pure transport (client.chat) then usage accounting."""
    result = await client.chat(session, purpose=purpose, messages=messages, tools=tools,
                               tool_choice=tool_choice, max_tokens=max_tokens)
    await usage.record(session, result.usage, purpose=purpose, user_id=user_id,
                       agency_id=agency_id, conversation_id=conversation_id)
    return result
