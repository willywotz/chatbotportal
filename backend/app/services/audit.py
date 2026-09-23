"""Record audit-trail entries. Best-effort: a failed audit write must never break
the action being audited."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.repositories import audit as audit_repo

logger = logging.getLogger(__name__)


async def record_audit(
    session: AsyncSession, actor, action: str, *, object_type=None, object_id=None, detail=None,
) -> None:
    try:
        await audit_repo.create(
            session,
            actor_id=getattr(actor, "id", None),
            actor_email=getattr(actor, "email", None),
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            detail=detail,
        )
    except Exception:
        logger.exception("failed to record audit entry: %s", action)


async def list_audit_log(
    session: AsyncSession,
    *,
    action: str | None = None,
    object_type: str | None = None,
    actor: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    return await audit_repo.list_and_count(
        session, action=action, object_type=object_type, actor=actor, offset=offset, limit=limit,
    )
