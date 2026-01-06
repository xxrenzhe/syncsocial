from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.account_run import AccountRun
from app.models.run import Run
from app.models.user import User
from app.schemas.run import AccountRunPublic, RunDetail, RunPublic

router = APIRouter()


@router.get("", response_model=list[RunPublic])
def list_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[RunPublic]:
    rows = db.scalars(select(Run).where(Run.workspace_id == user.workspace_id).order_by(Run.created_at.desc())).all()
    return [RunPublic.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RunDetail:
    run = db.get(Run, run_id)
    if run is None or run.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    account_runs = (
        db.scalars(select(AccountRun).where(AccountRun.workspace_id == user.workspace_id, AccountRun.run_id == run.id))
        .all()
    )
    return RunDetail(
        run=RunPublic.model_validate(run, from_attributes=True),
        account_runs=[AccountRunPublic.model_validate(ar, from_attributes=True) for ar in account_runs],
    )

