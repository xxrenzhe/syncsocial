from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.strategy import Strategy
from app.models.user import User
from app.schemas.strategy import CreateStrategyRequest, StrategyPublic, UpdateStrategyRequest

router = APIRouter()


@router.get("", response_model=list[StrategyPublic])
def list_strategies(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[StrategyPublic]:
    rows = (
        db.scalars(select(Strategy).where(Strategy.workspace_id == user.workspace_id).order_by(Strategy.created_at.desc()))
        .all()
    )
    return [StrategyPublic.model_validate(row, from_attributes=True) for row in rows]


@router.post("", response_model=StrategyPublic, status_code=status.HTTP_201_CREATED)
def create_strategy(
    payload: CreateStrategyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyPublic:
    platform_key = payload.platform_key.strip().lower()
    if not platform_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid platform_key")

    row = Strategy(workspace_id=user.workspace_id, name=payload.name, platform_key=platform_key, version=1, config=payload.config)
    db.add(row)
    db.commit()
    db.refresh(row)
    return StrategyPublic.model_validate(row, from_attributes=True)


@router.patch("/{strategy_id}", response_model=StrategyPublic)
def update_strategy(
    strategy_id: uuid.UUID,
    payload: UpdateStrategyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyPublic:
    row = db.get(Strategy, strategy_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if payload.name is not None:
        row.name = payload.name
    if payload.config is not None:
        row.config = payload.config
        row.version += 1

    db.add(row)
    db.commit()
    db.refresh(row)
    return StrategyPublic.model_validate(row, from_attributes=True)
