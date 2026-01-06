from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.deps import get_db, require_admin
from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.services.subscription import enforce_seat_limit, get_workspace_subscription
from app.models.user import User
from app.schemas.user import (
    AdminCreateUserRequest,
    AdminCreateUserResponse,
    AdminUpdateUserRequest,
    ResetPasswordResponse,
    UserPublic,
)

router = APIRouter()

_ALLOWED_ROLES = {"user", "admin"}
_ALLOWED_STATUSES = {"active", "disabled", "deleted"}
_ALLOWED_UPDATE_STATUSES = {"active", "disabled"}


def _generate_temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def _validate_role(role: str) -> None:
    if role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")


def _validate_status(status_value: str) -> None:
    if status_value not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")


def _validate_update_status(status_value: str) -> None:
    if status_value not in _ALLOWED_UPDATE_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")


@router.get("/users", response_model=list[UserPublic])
def list_users(
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> list[UserPublic]:
    users = db.scalars(select(User).where(User.workspace_id == admin.workspace_id).order_by(User.created_at.desc())).all()
    return [UserPublic.model_validate(user, from_attributes=True) for user in users]


@router.post("/users", response_model=AdminCreateUserResponse)
def create_user(
    payload: AdminCreateUserRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> AdminCreateUserResponse:
    _validate_role(payload.role)

    subscription = get_workspace_subscription(db, workspace_id=admin.workspace_id)
    try:
        enforce_seat_limit(db, workspace_id=admin.workspace_id, subscription=subscription)
    except ValueError as exc:
        if str(exc) == "SEAT_LIMIT_EXCEEDED":
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Seat limit exceeded; update subscription to add seats",
            ) from None
        raise

    existing = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if existing is not None and existing.status != "deleted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    initial_password = payload.temporary_password or _generate_temporary_password()
    if existing is not None and existing.status == "deleted":
        user = existing
        user.workspace_id = admin.workspace_id
        user.email = str(payload.email).lower()
        user.display_name = payload.display_name
        user.password_hash = hash_password(initial_password)
        user.role = payload.role
        user.status = "active"
        user.must_change_password = True
        db.add(user)
        db.flush()
    else:
        user = User(
            workspace_id=admin.workspace_id,
            email=str(payload.email).lower(),
            display_name=payload.display_name,
            password_hash=hash_password(initial_password),
            role=payload.role,
            status="active",
            must_change_password=True,
        )
        db.add(user)
        db.flush()

    db.add(
        AuditLog(
            workspace_id=admin.workspace_id,
            actor_user_id=admin.id,
            action="admin.user.create",
            target_type="user",
            target_id=user.id,
            metadata_={"email": user.email, "role": user.role},
        )
    )
    db.commit()

    return AdminCreateUserResponse(
        user=UserPublic.model_validate(user, from_attributes=True),
        initial_password=initial_password,
    )


@router.patch("/users/{user_id}", response_model=UserPublic)
def update_user(
    user_id: uuid.UUID,
    payload: AdminUpdateUserRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> UserPublic:
    user = db.get(User, user_id)
    if user is None or user.workspace_id != admin.workspace_id or user.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.status == "active" and user.status != "active":
        subscription = get_workspace_subscription(db, workspace_id=admin.workspace_id)
        try:
            enforce_seat_limit(db, workspace_id=admin.workspace_id, subscription=subscription)
        except ValueError as exc:
            if str(exc) == "SEAT_LIMIT_EXCEEDED":
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Seat limit exceeded; update subscription to add seats",
                ) from None
            raise

    if payload.role is not None:
        _validate_role(payload.role)
        user.role = payload.role
    if payload.status is not None:
        _validate_status(payload.status)
        _validate_update_status(payload.status)
        user.status = payload.status
    if payload.display_name is not None:
        user.display_name = payload.display_name

    db.add(
        AuditLog(
            workspace_id=admin.workspace_id,
            actor_user_id=admin.id,
            action="admin.user.update",
            target_type="user",
            target_id=user.id,
            metadata_={"role": payload.role, "status": payload.status},
        )
    )
    db.commit()
    db.refresh(user)
    return UserPublic.model_validate(user, from_attributes=True)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if user is None or user.workspace_id != admin.workspace_id or user.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    now = datetime.now(timezone.utc)
    user.status = "deleted"
    db.add(user)
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.add(
        AuditLog(
            workspace_id=admin.workspace_id,
            actor_user_id=admin.id,
            action="admin.user.delete",
            target_type="user",
            target_id=user.id,
            metadata_={"email": user.email},
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    user_id: uuid.UUID,
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> ResetPasswordResponse:
    user = db.get(User, user_id)
    if user is None or user.workspace_id != admin.workspace_id or user.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    temporary_password = _generate_temporary_password()
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    now = datetime.now(timezone.utc)
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    db.add(
        AuditLog(
            workspace_id=admin.workspace_id,
            actor_user_id=admin.id,
            action="admin.user.reset_password",
            target_type="user",
            target_id=user.id,
            metadata_={"at": datetime.now(timezone.utc).isoformat()},
        )
    )
    db.commit()
    return ResetPasswordResponse(temporary_password=temporary_password)
