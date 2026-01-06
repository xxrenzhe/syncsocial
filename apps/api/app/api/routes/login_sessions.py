from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.login_session import LoginSession
from app.models.user import User
from app.schemas.login_session import LoginSessionPublic
from app.utils.time import ensure_utc, utc_now

router = APIRouter()


def _expire_if_needed(db: Session, session: LoginSession) -> None:
    now = utc_now()
    expires_at = ensure_utc(session.expires_at)
    if session.status in {"created", "active"} and expires_at <= now:
        session.status = "expired"
        db.add(session)
        db.commit()


@router.get("/{login_session_id}", response_model=LoginSessionPublic)
def get_login_session(
    login_session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoginSessionPublic:
    row = db.get(LoginSession, login_session_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found")
    _expire_if_needed(db, row)
    db.refresh(row)
    return LoginSessionPublic.model_validate(row, from_attributes=True)


@router.post("/{login_session_id}/cancel")
def cancel_login_session(
    login_session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(LoginSession, login_session_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found")

    _expire_if_needed(db, row)
    if row.status in {"succeeded", "failed", "expired", "canceled"}:
        return {"ok": True, "status": row.status}

    row.status = "canceled"
    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status}
