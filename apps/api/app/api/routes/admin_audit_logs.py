from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, require_admin
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogPublic

router = APIRouter()


@router.get("/audit-logs", response_model=list[AuditLogPublic])
def list_audit_logs(
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> list[AuditLogPublic]:
    rows = db.execute(
        select(AuditLog, User.email)
        .join(User, User.id == AuditLog.actor_user_id, isouter=True)
        .where(AuditLog.workspace_id == admin.workspace_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    ).all()

    logs: list[AuditLogPublic] = []
    for log, actor_email in rows:
        logs.append(
            AuditLogPublic(
                id=log.id,
                workspace_id=log.workspace_id,
                actor_user_id=log.actor_user_id,
                actor_email=str(actor_email) if actor_email else None,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                metadata=log.metadata_ or {},
                created_at=log.created_at,
            )
        )
    return logs

