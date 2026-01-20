from __future__ import annotations

from datetime import timedelta
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import encrypt_json
from app.deps import get_current_user, get_db
from app.models.credential import Credential
from app.models.login_session import LoginSession
from app.models.proxy_pool import ProxyPool
from app.models.social_account import SocialAccount
from app.models.user import User
from app.platforms.registry import get_login_adapter
from app.schemas.credential import ImportCredentialRequest, ImportCredentialResponse
from app.schemas.login_session import LoginSessionPublic
from app.schemas.social_account import CreateSocialAccountRequest, SocialAccountPublic, UpdateSocialAccountRequest
from app.services.browser_cluster import browser_cluster
from app.services.fingerprint import generate_fingerprint_profile
from app.services.login_session_auto_capture import start_auto_capture
from app.services.proxy_selection import select_proxy_for_account
from app.services.subscription import enforce_max_social_accounts, get_workspace_subscription
from app.utils.time import utc_now

router = APIRouter()


@router.get("", response_model=list[SocialAccountPublic])
def list_social_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SocialAccountPublic]:
    rows = (
        db.scalars(
            select(SocialAccount)
            .where(SocialAccount.workspace_id == user.workspace_id)
            .order_by(SocialAccount.created_at.desc())
        )
        .all()
    )
    return [SocialAccountPublic.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{social_account_id}", response_model=SocialAccountPublic)
def get_social_account(
    social_account_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SocialAccountPublic:
    row = db.get(SocialAccount, social_account_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")
    return SocialAccountPublic.model_validate(row, from_attributes=True)


@router.delete("/{social_account_id}")
def delete_social_account(
    social_account_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(SocialAccount, social_account_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")

    row.status = "disabled"
    db.add(row)
    db.commit()
    return {"ok": True}


@router.post("", response_model=SocialAccountPublic, status_code=status.HTTP_201_CREATED)
def create_social_account(
    payload: CreateSocialAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SocialAccountPublic:
    platform_key = payload.platform_key.strip().lower()
    if not platform_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid platform_key")
    try:
        get_login_adapter(platform_key)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported platform_key") from None

    subscription = get_workspace_subscription(db, workspace_id=user.workspace_id)
    try:
        enforce_max_social_accounts(db, workspace_id=user.workspace_id, subscription=subscription)
    except ValueError as exc:
        if str(exc) == "SOCIAL_ACCOUNT_LIMIT_EXCEEDED":
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Social account limit exceeded; update subscription to add more accounts",
            ) from None
        raise

    row = SocialAccount(
        workspace_id=user.workspace_id,
        platform_key=platform_key,
        handle=payload.handle,
        display_name=payload.display_name,
        status="needs_login",
        labels=payload.labels,
        fingerprint_profile=generate_fingerprint_profile(platform_key=platform_key),
        proxy_pool_id=payload.proxy_pool_id,
    )
    if row.proxy_pool_id is not None:
        pool = db.get(ProxyPool, row.proxy_pool_id)
        if pool is None or pool.workspace_id != user.workspace_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid proxy_pool_id")
    db.add(row)
    db.commit()
    db.refresh(row)
    return SocialAccountPublic.model_validate(row, from_attributes=True)


@router.patch("/{social_account_id}", response_model=SocialAccountPublic)
def update_social_account(
    social_account_id: UUID,
    payload: UpdateSocialAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SocialAccountPublic:
    row = db.get(SocialAccount, social_account_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")

    if payload.handle is not None:
        row.handle = payload.handle
    if payload.display_name is not None:
        row.display_name = payload.display_name
    if "labels" in payload.model_fields_set:
        if payload.labels is None:
            row.labels = {}
        elif not isinstance(payload.labels, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid labels")
        else:
            row.labels = payload.labels
    if "proxy_pool_id" in payload.model_fields_set:
        if payload.proxy_pool_id is not None:
            pool = db.get(ProxyPool, payload.proxy_pool_id)
            if pool is None or pool.workspace_id != user.workspace_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid proxy_pool_id")
        row.proxy_pool_id = payload.proxy_pool_id

    db.add(row)
    db.commit()
    db.refresh(row)
    return SocialAccountPublic.model_validate(row, from_attributes=True)


@router.post("/{social_account_id}/login-sessions", response_model=LoginSessionPublic, status_code=status.HTTP_201_CREATED)
def create_login_session(
    social_account_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LoginSessionPublic:
    account = db.get(SocialAccount, social_account_id)
    if account is None or account.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")

    proxy = None
    if getattr(account, "proxy_pool_id", None):
        if settings.credential_encryption_key is None or not settings.credential_encryption_key.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CREDENTIAL_ENCRYPTION_KEY is required when using proxy pools",
            )
        from app.services.proxy_selection import select_proxy_for_account

        proxy = select_proxy_for_account(
            db,
            workspace_id=user.workspace_id,
            account_id=account.id,
            pool_id=account.proxy_pool_id,
        )

    now = utc_now()
    row = LoginSession(
        id=uuid.uuid4(),
        workspace_id=user.workspace_id,
        social_account_id=account.id,
        platform_key=account.platform_key,
        status="created",
        remote_url=None,
        expires_at=now + timedelta(minutes=30),
        created_by=user.id,
    )
    db.add(row)
    try:
        remote_url = browser_cluster.start_login_session(
            login_session_id=row.id,
            platform_key=account.platform_key,
            fingerprint_profile=getattr(account, "fingerprint_profile", None) or {},
            proxy=proxy or {},
        )
        row.status = "active"
        row.remote_url = remote_url
        db.add(row)
        db.commit()
        db.refresh(row)
        start_auto_capture(row.id)
    except Exception:
        row.status = "failed"
        db.add(row)
        db.commit()

    return LoginSessionPublic.model_validate(row, from_attributes=True)


@router.post("/{social_account_id}/credentials/import", response_model=ImportCredentialResponse)
def import_credential(
    social_account_id: UUID,
    payload: ImportCredentialRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportCredentialResponse:
    if settings.credential_encryption_key is None or not settings.credential_encryption_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CREDENTIAL_ENCRYPTION_KEY is required")

    account = db.get(SocialAccount, social_account_id)
    if account is None or account.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")

    ctype = str(payload.credential_type or "").strip().lower()
    storage_state: dict | None = None
    if ctype in {"storage_state", "storage"}:
        if not isinstance(payload.storage_state, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="storage_state is required")
        storage_state = payload.storage_state
    elif ctype in {"cookie_only", "cookies"}:
        if not isinstance(payload.cookies, list) or not payload.cookies:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cookies is required")
        storage_state = {"cookies": payload.cookies, "origins": []}
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credential_type")

    encrypted = encrypt_json(storage_state)
    now = utc_now()
    credential = db.scalar(
        select(Credential).where(
            Credential.workspace_id == user.workspace_id,
            Credential.social_account_id == account.id,
            Credential.credential_type == "storage_state",
        )
    )
    if credential is None:
        credential = Credential(
            workspace_id=user.workspace_id,
            social_account_id=account.id,
            credential_type="storage_state",
            encrypted_blob=encrypted,
            key_version=1,
            validated_at=None,
        )
    else:
        credential.encrypted_blob = encrypted
        credential.validated_at = None
    db.add(credential)
    db.commit()

    proxy = None
    if getattr(account, "proxy_pool_id", None):
        proxy = select_proxy_for_account(
            db,
            workspace_id=user.workspace_id,
            account_id=account.id,
            pool_id=account.proxy_pool_id,
        )

    try:
        result = browser_cluster.execute_action(
            platform_key=account.platform_key,
            action_type="health_check",
            storage_state=storage_state,
            fingerprint_profile=getattr(account, "fingerprint_profile", None) or {},
            proxy=proxy or {},
        )
    except Exception as exc:
        result = {"status": "failed", "error_code": "BROWSER_NODE_ERROR", "message": str(exc)}

    hc_status = str(result.get("status") or "failed")
    error_code = str(result.get("error_code")) if result.get("error_code") else None
    message = str(result.get("message")) if result.get("message") else None

    if hc_status == "succeeded":
        account.status = "healthy"
        account.last_health_check_at = now
        credential.validated_at = now
        db.add(account)
        db.add(credential)
        db.commit()
    else:
        # Keep consistent with worker behavior.
        if error_code in {"AUTH_REQUIRED", "CAPTCHA_REQUIRED"}:
            account.status = "needs_login"
        elif error_code == "ACCOUNT_LOCKED":
            account.status = "locked"
        account.last_health_check_at = now
        db.add(account)
        db.commit()

    return ImportCredentialResponse(
        account=SocialAccountPublic.model_validate(account, from_attributes=True),
        health_check_status=hc_status,
        error_code=error_code,
        message=message,
    )
