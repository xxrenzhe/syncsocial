from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.account_run import AccountRun
from app.models.run import Run
from app.models.schedule import Schedule
from app.models.social_account import SocialAccount
from app.models.strategy import Strategy
from app.models.user import User
from app.schemas.run import RunPublic
from app.schemas.schedule import CreateScheduleRequest, SchedulePublic, UpdateScheduleRequest
from app.services.schedule_planner import compute_next_run_at
from app.tasks.run_tasks import execute_account_run
from app.utils.time import utc_now

router = APIRouter()


def _resolve_accounts(db: Session, workspace_id: uuid.UUID, selector: dict) -> list[SocialAccount]:
    ids = selector.get("ids")
    if isinstance(ids, list) and ids:
        parsed: list[uuid.UUID] = []
        for item in ids:
            try:
                parsed.append(uuid.UUID(str(item)))
            except ValueError:
                continue
        if parsed:
            return db.scalars(
                select(SocialAccount).where(
                    SocialAccount.workspace_id == workspace_id,
                    SocialAccount.id.in_(parsed),
                )
            ).all()

    all_flag = selector.get("all")
    if all_flag is True:
        return db.scalars(select(SocialAccount).where(SocialAccount.workspace_id == workspace_id)).all()

    return db.scalars(
        select(SocialAccount).where(SocialAccount.workspace_id == workspace_id, SocialAccount.status == "healthy")
    ).all()


@router.get("", response_model=list[SchedulePublic])
def list_schedules(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SchedulePublic]:
    rows = (
        db.scalars(select(Schedule).where(Schedule.workspace_id == user.workspace_id).order_by(Schedule.created_at.desc()))
        .all()
    )
    return [SchedulePublic.model_validate(row, from_attributes=True) for row in rows]


@router.post("", response_model=SchedulePublic, status_code=status.HTTP_201_CREATED)
def create_schedule(
    payload: CreateScheduleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SchedulePublic:
    strategy = db.get(Strategy, payload.strategy_id)
    if strategy is None or strategy.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid strategy_id")

    selector = payload.account_selector or {"all": True}
    now = utc_now()
    row = Schedule(
        workspace_id=user.workspace_id,
        name=payload.name,
        enabled=payload.enabled,
        strategy_id=strategy.id,
        account_selector=selector,
        frequency=payload.frequency,
        schedule_spec=payload.schedule_spec,
        random_config=payload.random_config,
        max_parallel=payload.max_parallel,
        next_run_at=compute_next_run_at(
            frequency=payload.frequency,
            schedule_spec=payload.schedule_spec,
            random_config=payload.random_config,
            now=now,
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SchedulePublic.model_validate(row, from_attributes=True)


@router.patch("/{schedule_id}", response_model=SchedulePublic)
def update_schedule(
    schedule_id: uuid.UUID,
    payload: UpdateScheduleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SchedulePublic:
    row = db.get(Schedule, schedule_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    if payload.name is not None:
        row.name = payload.name
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.account_selector is not None:
        row.account_selector = payload.account_selector
    if payload.frequency is not None:
        row.frequency = payload.frequency
    if payload.schedule_spec is not None:
        row.schedule_spec = payload.schedule_spec
    if payload.random_config is not None:
        row.random_config = payload.random_config
    if payload.max_parallel is not None:
        row.max_parallel = payload.max_parallel

    if payload.frequency is not None or payload.schedule_spec is not None or payload.random_config is not None:
        row.next_run_at = compute_next_run_at(
            frequency=row.frequency,
            schedule_spec=row.schedule_spec or {},
            random_config=row.random_config or {},
            now=utc_now(),
        )

    db.add(row)
    db.commit()
    db.refresh(row)
    return SchedulePublic.model_validate(row, from_attributes=True)


@router.post("/{schedule_id}/run-now", response_model=RunPublic)
def run_now(
    schedule_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RunPublic:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None or schedule.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    if not schedule.enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Schedule disabled")

    strategy = db.get(Strategy, schedule.strategy_id)
    if strategy is None or strategy.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid strategy")

    accounts = _resolve_accounts(db, user.workspace_id, schedule.account_selector)
    run = Run(
        workspace_id=user.workspace_id,
        schedule_id=schedule.id,
        strategy_id=strategy.id,
        triggered_by=user.id,
        status="queued",
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()

    for account in accounts:
        db.add(
            AccountRun(
                workspace_id=user.workspace_id,
                run_id=run.id,
                social_account_id=account.id,
                status="queued",
            )
        )

    db.commit()
    db.refresh(run)

    account_run_ids = db.scalars(select(AccountRun.id).where(AccountRun.run_id == run.id)).all()
    for account_run_id in account_run_ids:
        try:
            execute_account_run.delay(str(account_run_id))
        except Exception:
            pass

    schedule.last_run_at = utc_now()
    schedule.next_run_at = compute_next_run_at(
        frequency=schedule.frequency,
        schedule_spec=schedule.schedule_spec or {},
        random_config=schedule.random_config or {},
        now=utc_now(),
    )
    db.add(schedule)
    db.commit()

    return RunPublic.model_validate(run, from_attributes=True)
