from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.action import Action
from app.models.artifact import Artifact
from app.models.user import User
from app.schemas.action import ActionPublic
from app.schemas.artifact import ArtifactPublic

router = APIRouter()


@router.get("/actions/{action_id}", response_model=ActionPublic)
def get_action(action_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ActionPublic:
    row = db.get(Action, action_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    artifacts = (
        db.scalars(
            select(Artifact)
            .where(Artifact.workspace_id == user.workspace_id, Artifact.action_id == row.id)
            .order_by(Artifact.created_at.asc())
        )
        .all()
    )
    metadata = row.metadata_ if isinstance(row.metadata_, dict) else {}
    return ActionPublic(
        id=row.id,
        workspace_id=row.workspace_id,
        account_run_id=row.account_run_id,
        action_type=row.action_type,
        platform_key=row.platform_key,
        target_external_id=row.target_external_id,
        target_url=row.target_url,
        idempotency_key=row.idempotency_key,
        status=row.status,
        error_code=row.error_code,
        metadata=metadata,
        artifacts=[ArtifactPublic.model_validate(a, from_attributes=True) for a in artifacts],
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


@router.get("/actions/{action_id}/artifacts", response_model=list[ArtifactPublic])
def list_action_artifacts(
    action_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ArtifactPublic]:
    row = db.get(Action, action_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    artifacts = (
        db.scalars(
            select(Artifact)
            .where(Artifact.workspace_id == user.workspace_id, Artifact.action_id == row.id)
            .order_by(Artifact.created_at.asc())
        )
        .all()
    )
    return [ArtifactPublic.model_validate(a, from_attributes=True) for a in artifacts]

