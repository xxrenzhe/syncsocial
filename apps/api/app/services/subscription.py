from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.subscription import WorkspaceSubscription, WorkspaceUsageMonthly
from app.models.user import User
from app.utils.time import ensure_utc

_ACTIVE_STATUSES = {"trial", "active"}


@dataclass(frozen=True)
class SubscriptionCheckResult:
    allowed: bool
    reason: str | None


def get_workspace_subscription(db: Session, *, workspace_id) -> WorkspaceSubscription | None:
    return db.scalar(select(WorkspaceSubscription).where(WorkspaceSubscription.workspace_id == workspace_id))


def is_subscription_active(subscription: WorkspaceSubscription | None, *, now: datetime) -> SubscriptionCheckResult:
    if subscription is None:
        return SubscriptionCheckResult(allowed=True, reason=None)

    now_utc = ensure_utc(now)
    status = str(subscription.status or "").strip().lower()
    if status not in _ACTIVE_STATUSES:
        return SubscriptionCheckResult(allowed=False, reason="SUBSCRIPTION_INACTIVE")

    if subscription.current_period_end is not None:
        end = ensure_utc(subscription.current_period_end)
        if end <= now_utc:
            return SubscriptionCheckResult(allowed=False, reason="SUBSCRIPTION_EXPIRED")

    return SubscriptionCheckResult(allowed=True, reason=None)


def get_current_month_period_start(now: datetime) -> date:
    now_utc = ensure_utc(now)
    return date(now_utc.year, now_utc.month, 1)


def get_workspace_usage_monthly(db: Session, *, workspace_id, period_start: date) -> WorkspaceUsageMonthly | None:
    return db.scalar(
        select(WorkspaceUsageMonthly).where(
            WorkspaceUsageMonthly.workspace_id == workspace_id,
            WorkspaceUsageMonthly.period_start == period_start,
        )
    )


def increment_automation_runtime_seconds(
    db: Session,
    *,
    workspace_id,
    started_at: datetime | None,
    finished_at: datetime | None,
) -> int:
    if started_at is None or finished_at is None:
        return 0

    start = ensure_utc(started_at)
    end = ensure_utc(finished_at)
    seconds = int((end - start).total_seconds())
    if seconds <= 0:
        return 0

    period_start = get_current_month_period_start(end)
    bind = db.get_bind()
    if bind is not None and getattr(bind.dialect, "name", "") == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(WorkspaceUsageMonthly).values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            period_start=period_start,
            automation_runtime_seconds=seconds,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["workspace_id", "period_start"],
            set_={
                "automation_runtime_seconds": WorkspaceUsageMonthly.automation_runtime_seconds + stmt.excluded.automation_runtime_seconds,
                "updated_at": func.now(),
            },
        )
        db.execute(stmt)
        return seconds

    usage = get_workspace_usage_monthly(db, workspace_id=workspace_id, period_start=period_start)
    if usage is None:
        usage = WorkspaceUsageMonthly(workspace_id=workspace_id, period_start=period_start, automation_runtime_seconds=0)
        db.add(usage)
        db.flush()

    usage.automation_runtime_seconds = int(usage.automation_runtime_seconds or 0) + seconds
    db.add(usage)
    return seconds


def has_remaining_runtime_quota(
    subscription: WorkspaceSubscription | None,
    usage: WorkspaceUsageMonthly | None,
) -> SubscriptionCheckResult:
    if subscription is None:
        return SubscriptionCheckResult(allowed=True, reason=None)

    quota_hours = subscription.automation_runtime_hours
    if quota_hours is None:
        return SubscriptionCheckResult(allowed=True, reason=None)
    try:
        quota_seconds = int(quota_hours) * 3600
    except Exception:
        return SubscriptionCheckResult(allowed=True, reason=None)
    if quota_seconds <= 0:
        return SubscriptionCheckResult(allowed=True, reason=None)

    used = int(usage.automation_runtime_seconds) if usage is not None and usage.automation_runtime_seconds is not None else 0
    if used >= quota_seconds:
        return SubscriptionCheckResult(allowed=False, reason="RUNTIME_QUOTA_EXCEEDED")
    return SubscriptionCheckResult(allowed=True, reason=None)


def enforce_seat_limit(db: Session, *, workspace_id, subscription: WorkspaceSubscription | None) -> None:
    if subscription is None:
        return
    seats = subscription.seats
    try:
        seat_limit = int(seats)
    except Exception:
        return
    if seat_limit <= 0:
        return

    active_count = db.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.workspace_id == workspace_id,
            User.status == "active",
        )
    )
    if active_count is not None and int(active_count) >= seat_limit:
        raise ValueError("SEAT_LIMIT_EXCEEDED")


def enforce_max_social_accounts(db: Session, *, workspace_id, subscription: WorkspaceSubscription | None) -> None:
    if subscription is None:
        return
    limit = subscription.max_social_accounts
    if limit is None:
        return
    try:
        max_value = int(limit)
    except Exception:
        return
    if max_value <= 0:
        raise ValueError("SOCIAL_ACCOUNT_LIMIT_EXCEEDED")

    from app.models.social_account import SocialAccount

    count_value = db.scalar(
        select(func.count())
        .select_from(SocialAccount)
        .where(SocialAccount.workspace_id == workspace_id)
    )
    if count_value is not None and int(count_value) >= max_value:
        raise ValueError("SOCIAL_ACCOUNT_LIMIT_EXCEEDED")


def effective_parallel_limit(subscription: WorkspaceSubscription | None, *, schedule_max_parallel: int) -> int:
    candidate = schedule_max_parallel if schedule_max_parallel and schedule_max_parallel > 0 else 1
    if subscription is None or subscription.max_parallel_sessions is None:
        return candidate
    try:
        quota = int(subscription.max_parallel_sessions)
    except Exception:
        return candidate
    if quota <= 0:
        return candidate
    return max(1, min(candidate, quota))
