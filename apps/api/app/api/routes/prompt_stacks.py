from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.prompt_stack import PromptStack
from app.models.user import User
from app.schemas.prompt_stack import (
    PromptStackPreviewRequest,
    PromptStackPreviewResponse,
    PromptStackPublic,
    UpsertPromptStackRequest,
)
from app.services.prompt_stack_engine import generate_prompt_from_stack

router = APIRouter()


@router.get("", response_model=list[PromptStackPublic])
def list_prompt_stacks(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[PromptStackPublic]:
    rows = (
        db.scalars(
            select(PromptStack).where(PromptStack.workspace_id == user.workspace_id).order_by(PromptStack.updated_at.desc())
        )
        .all()
    )
    return [PromptStackPublic.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{key}", response_model=PromptStackPublic)
def get_prompt_stack(key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PromptStackPublic:
    normalized = key.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key")

    row = db.scalar(select(PromptStack).where(PromptStack.workspace_id == user.workspace_id, PromptStack.key == normalized))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt stack not found")
    return PromptStackPublic.model_validate(row, from_attributes=True)


@router.put("/{key}", response_model=PromptStackPublic)
def upsert_prompt_stack(
    key: str,
    payload: UpsertPromptStackRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PromptStackPublic:
    normalized = key.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key")

    row = db.scalar(select(PromptStack).where(PromptStack.workspace_id == user.workspace_id, PromptStack.key == normalized))
    if row is None:
        row = PromptStack(workspace_id=user.workspace_id, key=normalized, version=1, payload=payload.payload)
    else:
        row.payload = payload.payload
        row.version = int(row.version or 0) + 1

    db.add(row)
    db.commit()
    db.refresh(row)
    return PromptStackPublic.model_validate(row, from_attributes=True)


@router.post("/{key}/preview", response_model=PromptStackPreviewResponse)
def preview_prompt_stack(
    key: str,
    payload: PromptStackPreviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PromptStackPreviewResponse:
    normalized = key.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key")

    stack_payload = payload.payload
    if stack_payload is None:
        row = db.scalar(select(PromptStack).where(PromptStack.workspace_id == user.workspace_id, PromptStack.key == normalized))
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt stack not found")
        stack_payload = row.payload if isinstance(row.payload, dict) else {}

    try:
        text = generate_prompt_from_stack(stack_payload, seed=payload.seed)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return PromptStackPreviewResponse(text=text)

