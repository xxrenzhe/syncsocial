from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_json
from app.deps import get_current_user, get_db
from app.models.credential import Credential
from app.models.login_session import LoginSession
from app.models.social_account import SocialAccount
from app.models.user import User
from app.schemas.login_session import LoginSessionPublic
from app.services.browser_cluster import browser_cluster
from app.utils.time import ensure_utc, utc_now

router = APIRouter()


def _expire_if_needed(db: Session, session: LoginSession) -> None:
    now = utc_now()
    expires_at = ensure_utc(session.expires_at)
    if session.status in {"created", "active"} and expires_at <= now:
        session.status = "expired"
        db.add(session)
        db.commit()
        try:
            browser_cluster.stop_login_session(login_session_id=session.id)
        except Exception:
            pass


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
    try:
        browser_cluster.stop_login_session(login_session_id=row.id)
    except Exception:
        pass
    return {"ok": True, "status": row.status}


@router.post("/{login_session_id}/finalize", response_model=LoginSessionPublic)
def finalize_login_session(
    login_session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoginSessionPublic:
    row = db.get(LoginSession, login_session_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found")

    _expire_if_needed(db, row)
    db.refresh(row)

    if row.status in {"expired", "canceled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Login session is {row.status}")
    if row.status == "succeeded":
        return LoginSessionPublic.model_validate(row, from_attributes=True)

    try:
        logged_in = browser_cluster.is_logged_in(login_session_id=row.id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login session runtime not found") from None

    if not logged_in:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not logged in yet")

    storage_state = browser_cluster.export_storage_state(login_session_id=row.id)
    try:
        encrypted_blob = encrypt_json(storage_state)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    credential = db.scalar(
        select(Credential).where(
            Credential.workspace_id == row.workspace_id,
            Credential.social_account_id == row.social_account_id,
            Credential.credential_type == "storage_state",
        )
    )
    if credential is None:
        credential = Credential(
            workspace_id=row.workspace_id,
            social_account_id=row.social_account_id,
            credential_type="storage_state",
            encrypted_blob=encrypted_blob,
            key_version=1,
        )
        db.add(credential)
    else:
        credential.encrypted_blob = encrypted_blob
        db.add(credential)

    account = db.get(SocialAccount, row.social_account_id)
    if account is not None:
        account.status = "healthy"
        db.add(account)

    row.status = "succeeded"
    db.add(row)
    db.commit()
    db.refresh(row)

    try:
        browser_cluster.stop_login_session(login_session_id=row.id)
    except Exception:
        pass

    return LoginSessionPublic.model_validate(row, from_attributes=True)
