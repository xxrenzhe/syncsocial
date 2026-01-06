from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_db, require_admin
from app.models.audit_log import AuditLog
from app.models.subscription import WorkspaceSubscription
from app.models.user import User
from app.schemas.subscription import (
    AdminSubscriptionOverview,
    AdminUpsertWorkspaceSubscriptionRequest,
    WorkspaceSubscriptionPublic,
    WorkspaceUsageMonthlyPublic,
)
from app.services.subscription import (
    get_current_month_period_start,
    get_workspace_subscription,
    get_workspace_usage_monthly,
    is_subscription_active,
)
from app.utils.time import utc_now

router = APIRouter()

_ALLOWED_STATUSES = {"trial", "active", "past_due", "suspended", "canceled"}


def _validate_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized or normalized not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid subscription status")
    return normalized


@router.get("/subscription", response_model=AdminSubscriptionOverview)
def get_subscription_overview(
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> AdminSubscriptionOverview:
    sub = get_workspace_subscription(db, workspace_id=admin.workspace_id)
    now = utc_now()
    period_start = get_current_month_period_start(now)
    usage = get_workspace_usage_monthly(db, workspace_id=admin.workspace_id, period_start=period_start)

    active_check = is_subscription_active(sub, now=now)

    return AdminSubscriptionOverview(
        subscription=WorkspaceSubscriptionPublic.model_validate(sub, from_attributes=True) if sub is not None else None,
        current_month_usage=WorkspaceUsageMonthlyPublic.model_validate(usage, from_attributes=True) if usage is not None else None,
        active=active_check.allowed,
        active_reason=active_check.reason,
    )


@router.put("/subscription", response_model=WorkspaceSubscriptionPublic)
def upsert_subscription(
    payload: AdminUpsertWorkspaceSubscriptionRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> WorkspaceSubscriptionPublic:
    status_value = _validate_status(payload.status)
    plan_key = str(payload.plan_key or "").strip() or "trial"

    sub = get_workspace_subscription(db, workspace_id=admin.workspace_id)
    if sub is None:
        sub = WorkspaceSubscription(workspace_id=admin.workspace_id)

    sub.status = status_value
    sub.plan_key = plan_key
    sub.seats = int(payload.seats)
    sub.max_social_accounts = payload.max_social_accounts
    sub.max_parallel_sessions = payload.max_parallel_sessions
    sub.automation_runtime_hours = payload.automation_runtime_hours
    sub.artifact_retention_days = payload.artifact_retention_days
    sub.current_period_start = payload.current_period_start
    sub.current_period_end = payload.current_period_end

    db.add(sub)
    db.add(
        AuditLog(
            workspace_id=admin.workspace_id,
            actor_user_id=admin.id,
            action="admin.subscription.upsert",
            target_type="workspace_subscription",
            target_id=sub.id,
            metadata_={
                "status": sub.status,
                "plan_key": sub.plan_key,
                "seats": sub.seats,
                "max_social_accounts": sub.max_social_accounts,
                "max_parallel_sessions": sub.max_parallel_sessions,
                "automation_runtime_hours": sub.automation_runtime_hours,
                "artifact_retention_days": sub.artifact_retention_days,
                "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            },
        )
    )
    db.commit()
    db.refresh(sub)
    return WorkspaceSubscriptionPublic.model_validate(sub, from_attributes=True)

