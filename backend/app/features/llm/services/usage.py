import logging

from app.features.llm.repositories import llm_usage as llm_usage_repo

logger = logging.getLogger(__name__)


async def record(session, usage_metadata, *, purpose, user_id=None,
                 agency_id=None, conversation_id=None) -> None:
    from app.core.usage_context import current_user_id
    try:
        for model, tokens in (usage_metadata or {}).items():
            await llm_usage_repo.create(
                session,
                model=model, purpose=purpose,
                prompt_tokens=tokens.get("input_tokens", 0),
                completion_tokens=tokens.get("output_tokens", 0),
                cost_usd=tokens.get("cost"),
                user_id=user_id if user_id is not None else current_user_id.get(),
                agency_id=agency_id, conversation_id=conversation_id,
            )
    except Exception:
        logger.exception("failed to record llm usage")
