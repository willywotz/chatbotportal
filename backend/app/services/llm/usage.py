import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import llm_usage as llm_usage_repo
from app.services.llm.client import LlmUsageInfo

logger = logging.getLogger(__name__)


async def record(session: AsyncSession, usage: LlmUsageInfo, *, purpose, user_id=None, agency_id=None,
                 conversation_id=None) -> None:
    """Persist one LLM usage row. Accounting must never break the call path."""
    from app.services.usage_context import current_user_id
    try:
        await llm_usage_repo.create(
            session,
            model=usage.model, purpose=purpose,
            prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
            cost_usd=usage.cost_usd,
            user_id=user_id if user_id is not None else current_user_id.get(),
            agency_id=agency_id, conversation_id=conversation_id,
        )
    except Exception:  # accounting must never break the call path
        logger.exception("failed to record llm usage")
