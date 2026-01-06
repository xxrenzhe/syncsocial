from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    maybe_rehash_password,
    verify_password,
)
from app.deps import get_db, get_request_client_info
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    new_hash = maybe_rehash_password(payload.password, user.password_hash)
    if new_hash is not None:
        user.password_hash = new_hash

    user.last_login_at = datetime.now(timezone.utc)

    access_token, access_expires_at = create_access_token(
        user_id=str(user.id),
        workspace_id=str(user.workspace_id),
        role=user.role,
    )

    refresh_token = generate_refresh_token()
    refresh_token_hash = hash_refresh_token(refresh_token)
    refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    user_agent, ip = get_request_client_info(request)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            expires_at=refresh_expires_at,
            user_agent=user_agent,
            ip=ip,
        )
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_expires_at,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    token_hash = hash_refresh_token(payload.refresh_token)
    refresh_row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if refresh_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if refresh_row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    now = datetime.now(timezone.utc)
    if refresh_row.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db.get(User, refresh_row.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User disabled or not found")

    access_token, access_expires_at = create_access_token(
        user_id=str(user.id),
        workspace_id=str(user.workspace_id),
        role=user.role,
    )

    refresh_row.revoked_at = now
    new_refresh_token = generate_refresh_token()
    new_hash = hash_refresh_token(new_refresh_token)
    new_expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    user_agent, ip = get_request_client_info(request)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=new_hash,
            expires_at=new_expires_at,
            user_agent=user_agent,
            ip=ip,
        )
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        access_token_expires_at=access_expires_at,
    )


@router.post("/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> dict:
    token_hash = hash_refresh_token(payload.refresh_token)
    refresh_row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if refresh_row is None:
        return {"ok": True}
    if refresh_row.revoked_at is None:
        refresh_row.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}
