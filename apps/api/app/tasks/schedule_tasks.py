from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.account_run import AccountRun
from app.models.run import Run
from app.models.schedule import Schedule
from app.models.social_account import SocialAccount
from app.models.strategy import Strategy
from app.services.schedule_planner import compute_next_run_at, should_skip_run
from app.tasks.run_tasks import execute_account_run
from app.utils.time import utc_now


@celery_app.task(name="syncsocial.tick_schedules")
def tick_schedules() -> None:
    now = utc_now()

    with SessionLocal() as db:
        schedules = (
            db.scalars(
                select(Schedule)
                .where(Schedule.enabled.is_(True), Schedule.frequency != "manual")
                .order_by(Schedule.created_at.asc())
            )
            .all()
        )
        if not schedules:
            return

        for schedule in schedules:
            if schedule.next_run_at is None:
                schedule.next_run_at = compute_next_run_at(
                    frequency=schedule.frequency,
                    schedule_spec=schedule.schedule_spec or {},
                    random_config=schedule.random_config or {},
                    now=now,
                )
                db.add(schedule)
        db.commit()

        due_schedules = (
            db.scalars(
                select(Schedule)
                .where(
                    Schedule.enabled.is_(True),
                    Schedule.frequency != "manual",
                    Schedule.next_run_at.is_not(None),
                    Schedule.next_run_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
            .all()
        )

        for schedule in due_schedules:
            if _has_running_run(db, schedule.id):
                continue

            strategy = db.get(Strategy, schedule.strategy_id)
            if strategy is None:
                schedule.next_run_at = compute_next_run_at(
                    frequency=schedule.frequency,
                    schedule_spec=schedule.schedule_spec or {},
                    random_config=schedule.random_config or {},
                    now=now,
                )
                schedule.last_run_at = now
                db.add(schedule)
                db.commit()
                continue

            if should_skip_run(random_config=schedule.random_config or {}):
                schedule.last_run_at = now
                schedule.next_run_at = compute_next_run_at(
                    frequency=schedule.frequency,
                    schedule_spec=schedule.schedule_spec or {},
                    random_config=schedule.random_config or {},
                    now=now,
                )
                db.add(schedule)
                db.commit()
                continue

            run, account_run_ids = _create_run_for_schedule(db, schedule, strategy, now)
            if run is None:
                continue

            for account_run_id in account_run_ids:
                try:
                    execute_account_run.delay(str(account_run_id))
                except Exception:
                    pass


def _has_running_run(db, schedule_id) -> bool:
    running_count = db.scalar(
        select(func.count())
        .select_from(Run)
        .where(Run.schedule_id == schedule_id, Run.status.in_(["queued", "running"]))
    )
    return bool(running_count and int(running_count) > 0)


def _create_run_for_schedule(
    db,
    schedule: Schedule,
    strategy: Strategy,
    now: datetime,
) -> tuple[Run, list[uuid.UUID]]:
    accounts = _resolve_accounts(db, schedule.workspace_id, schedule.account_selector or {})
    run = Run(
        workspace_id=schedule.workspace_id,
        schedule_id=schedule.id,
        strategy_id=strategy.id,
        triggered_by=None,
        status="queued",
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()

    account_run_ids: list[uuid.UUID] = []
    for account in accounts:
        ar = AccountRun(
            workspace_id=schedule.workspace_id,
            run_id=run.id,
            social_account_id=account.id,
            status="queued",
        )
        db.add(ar)
        db.flush()
        account_run_ids.append(ar.id)

    schedule.last_run_at = now
    schedule.next_run_at = compute_next_run_at(
        frequency=schedule.frequency,
        schedule_spec=schedule.schedule_spec or {},
        random_config=schedule.random_config or {},
        now=now,
    )
    db.add(schedule)
    db.commit()
    db.refresh(run)
    return run, account_run_ids


def _resolve_accounts(db, workspace_id, selector: dict) -> list[SocialAccount]:
    ids = selector.get("ids")
    if isinstance(ids, list) and ids:
        parsed: list[uuid.UUID] = []
        for item in ids:
            try:
                parsed.append(uuid.UUID(str(item)))
            except Exception:
                continue
        if parsed:
            rows = db.scalars(
                select(SocialAccount).where(
                    SocialAccount.workspace_id == workspace_id,
                    SocialAccount.id.in_(parsed),
                )
            ).all()
            return rows

    if selector.get("all") is True:
        return db.scalars(select(SocialAccount).where(SocialAccount.workspace_id == workspace_id)).all()

    return db.scalars(
        select(SocialAccount).where(SocialAccount.workspace_id == workspace_id, SocialAccount.status == "healthy")
    ).all()
