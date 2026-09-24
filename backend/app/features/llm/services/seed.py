from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services.purpose import Purpose


async def seed_llm_defaults(session: AsyncSession) -> None:
    """Insert one default provider and a binding per purpose from env settings.

    Never overwrites edits.
    """
    provider = await llm_repo.get_provider_by_name(session, "default")
    if provider is None:
        provider = await llm_repo.create_provider(
            session,
            name="default",
            provider="openai",
            model=settings.LLM_DEFAULT_MODEL,
            base_url=settings.LLM_BASE_URL or None,
            api_key=settings.LLM_API_KEY,
            timeout_seconds=float(settings.LLM_CALL_TIMEOUT),
        )
    for purpose in Purpose:
        if await llm_repo.get_binding_by_purpose(session, purpose) is None:
            await llm_repo.create_binding(
                session, purpose=purpose, provider_id=provider.id)
