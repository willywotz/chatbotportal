import logging

from app.services.llm.client import LlmUsageInfo

logger = logging.getLogger(__name__)


async def record(usage: LlmUsageInfo, *, purpose, user_id=None, agency_id=None,
                 conversation_id=None) -> None:
    """Persist one LLM usage row. Accounting must never break the call path."""
    from app.models import LlmUsage
    from app.services.usage_context import current_api_key_id, current_user_id
    try:
        await LlmUsage.create(
            model=usage.model, purpose=purpose,
            prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
            cost_usd=usage.cost_usd,
            user_id=user_id if user_id is not None else current_user_id.get(),
            agency_id=agency_id, conversation_id=conversation_id,
            api_key_id=current_api_key_id.get(),
        )
    except Exception:  # accounting must never break the call path
        logger.exception("failed to record llm usage")
