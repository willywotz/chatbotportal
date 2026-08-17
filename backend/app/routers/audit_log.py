"""Admin-only view of the audit trail."""
from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import require_admin
from app.models import AuditLog
from app.models.user import User
from app.services import audit as audit_service

router = APIRouter(prefix="/audit-log", tags=["Audit"])


def _row(a: AuditLog) -> dict:
    return {
        "id": str(a.id),
        "actor_id": str(a.actor_id) if a.actor_id else None,
        "actor_email": a.actor_email,
        "action": a.action,
        "object_type": a.object_type,
        "object_id": a.object_id,
        "detail": a.detail,
        "created_at": str(a.created_at),
    }


async def list_audit_log(
    action: str | None = None,
    object_type: str | None = None,
    actor: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: User = None,
) -> dict:
    rows, total = await audit_service.list_audit_log(
        action=action, object_type=object_type, actor=actor, limit=limit, offset=offset,
    )
    return {"data": [_row(a) for a in rows], "total": total}


@router.get("/", summary="List audit-trail entries (admin)")
async def get_audit_log(
    action: str | None = Query(None),
    object_type: str | None = Query(None),
    actor: str | None = Query(None, description="actor_email substring (case-insensitive)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: User = Depends(require_admin),
) -> dict:
    return await list_audit_log(
        action=action,
        object_type=object_type,
        actor=actor,
        limit=limit,
        offset=offset,
        _admin=_admin,
    )
