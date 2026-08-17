"""Record audit-trail entries. Best-effort: a failed audit write must never break
the action being audited."""
import logging

from app.models import AuditLog

logger = logging.getLogger(__name__)


async def record_audit(actor, action: str, *, object_type=None, object_id=None, detail=None) -> None:
    try:
        await AuditLog.create(
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
    *,
    action: str | None = None,
    object_type: str | None = None,
    actor: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    qs = AuditLog.all()
    if action:
        qs = qs.filter(action=action)
    if object_type:
        qs = qs.filter(object_type=object_type)
    if actor:
        qs = qs.filter(actor_email__icontains=actor)
    total = await qs.count()
    rows = await qs.order_by("-created_at").offset(offset).limit(limit)
    return rows, total
