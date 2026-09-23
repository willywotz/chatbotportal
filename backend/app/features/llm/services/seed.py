from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.llm.repositories import llm as llm_repo
from app.features.llm.services.purpose import Purpose


async def seed_llm_defaults(session: AsyncSession) -> None:
    """Insert default providers/routes from env settings. Never overwrites edits."""
    openrouter = await llm_repo.get_provider_by_name(session, "openrouter")
    if openrouter is None:
        openrouter = await llm_repo.create_provider(
            session,
            name="openrouter",
            base_url=settings.OPENROUTER_API_URL,
            api_key=settings.OPENROUTER_API_KEY,
            auth_header="Authorization",
            auth_scheme="Bearer",
            timeout_seconds=float(settings.LLM_CALL_TIMEOUT),
            request_usage=True,
        )
    thaillm = await llm_repo.get_provider_by_name(session, "thaillm")
    if thaillm is None:
        thaillm = await llm_repo.create_provider(
            session,
            name="thaillm",
            base_url=settings.PARSE_SPEC_URL,
            api_key=settings.PARSE_SPEC_API_KEY,
            auth_header="apikey",
            auth_scheme="",
            timeout_seconds=float(settings.PARSE_SPEC_TIMEOUT),
            request_usage=False,
        )
    routes = [
        (Purpose.CLASSIFICATION, openrouter, settings.CLASSIFICATION_MODEL, None),
        (Purpose.BRIEF, openrouter, settings.CLASSIFICATION_MODEL, float(settings.WEEKLY_BRIEF_TIMEOUT)),
        (Purpose.JUDGE, openrouter, settings.CLASSIFICATION_MODEL, None),
        (Purpose.PARSE_SPEC, thaillm, settings.PARSE_SPEC_LLM_MODEL, None),
        # Falls back to the classification model/provider until configured otherwise.
        (Purpose.POPULAR_QUESTIONS, openrouter, settings.CLASSIFICATION_MODEL, None),
    ]
    for purpose, provider, model, timeout_override in routes:
        if await llm_repo.get_route_by_purpose(session, purpose) is None:
            await llm_repo.create_route(
                session, purpose=purpose, provider=provider, model=model,
                timeout_override=timeout_override,
            )
