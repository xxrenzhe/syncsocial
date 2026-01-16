from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_json, encrypt_json
from app.deps import get_current_user, get_db
from app.models.proxy import Proxy
from app.models.proxy_pool import ProxyPool
from app.models.user import User
from app.schemas.proxy import (
    CreateProxyPoolRequest,
    CreateProxyRequest,
    ProxyPoolPublic,
    ProxyPublic,
    UpdateProxyPoolRequest,
    UpdateProxyRequest,
)
from app.services.browser_cluster import browser_cluster
from app.utils.time import utc_now

router = APIRouter()

_ALLOWED_POOL_STRATEGIES = {"hash", "random"}
_ALLOWED_SCHEMES = {"http", "https", "socks5"}


def _require_encryption_key() -> None:
    if settings.credential_encryption_key is None or not settings.credential_encryption_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CREDENTIAL_ENCRYPTION_KEY is required to store proxy credentials",
        )


def _normalize_strategy(strategy: str) -> str:
    normalized = str(strategy or "").strip().lower()
    if normalized not in _ALLOWED_POOL_STRATEGIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid proxy pool strategy")
    return normalized


def _normalize_scheme(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _ALLOWED_SCHEMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid proxy scheme")
    return normalized


@router.get("/proxy-pools", response_model=list[ProxyPoolPublic])
def list_proxy_pools(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ProxyPoolPublic]:
    rows = (
        db.scalars(select(ProxyPool).where(ProxyPool.workspace_id == user.workspace_id).order_by(ProxyPool.created_at.desc()))
        .all()
    )
    return [ProxyPoolPublic.model_validate(row, from_attributes=True) for row in rows]


@router.post("/proxy-pools", response_model=ProxyPoolPublic, status_code=status.HTTP_201_CREATED)
def create_proxy_pool(
    payload: CreateProxyPoolRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProxyPoolPublic:
    strategy = _normalize_strategy(payload.strategy)
    row = ProxyPool(workspace_id=user.workspace_id, name=payload.name.strip(), strategy=strategy)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ProxyPoolPublic.model_validate(row, from_attributes=True)


@router.patch("/proxy-pools/{pool_id}", response_model=ProxyPoolPublic)
def update_proxy_pool(
    pool_id: uuid.UUID,
    payload: UpdateProxyPoolRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProxyPoolPublic:
    row = db.get(ProxyPool, pool_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy pool not found")
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.strategy is not None:
        row.strategy = _normalize_strategy(payload.strategy)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ProxyPoolPublic.model_validate(row, from_attributes=True)


@router.delete("/proxy-pools/{pool_id}")
def delete_proxy_pool(
    pool_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(ProxyPool, pool_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy pool not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/proxy-pools/{pool_id}/proxies", response_model=list[ProxyPublic])
def list_proxies(
    pool_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProxyPublic]:
    pool = db.get(ProxyPool, pool_id)
    if pool is None or pool.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy pool not found")
    rows = db.scalars(select(Proxy).where(Proxy.pool_id == pool_id, Proxy.workspace_id == user.workspace_id).order_by(Proxy.created_at.desc())).all()
    return [ProxyPublic.model_validate(row, from_attributes=True) for row in rows]


@router.post("/proxy-pools/{pool_id}/proxies", response_model=ProxyPublic, status_code=status.HTTP_201_CREATED)
def create_proxy(
    pool_id: uuid.UUID,
    payload: CreateProxyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProxyPublic:
    _require_encryption_key()
    pool = db.get(ProxyPool, pool_id)
    if pool is None or pool.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy pool not found")

    scheme = _normalize_scheme(payload.scheme)
    host = payload.host.strip()
    auth_blob = encrypt_json({"username": payload.username, "password": payload.password})

    row = Proxy(
        workspace_id=user.workspace_id,
        pool_id=pool_id,
        scheme=scheme,
        host=host,
        port=int(payload.port),
        country=(payload.country.strip().upper()[:2] if isinstance(payload.country, str) and payload.country.strip() else None),
        auth_encrypted=auth_blob,
        enabled=bool(payload.enabled),
        weight=int(payload.weight),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ProxyPublic.model_validate(row, from_attributes=True)


@router.patch("/proxies/{proxy_id}", response_model=ProxyPublic)
def update_proxy(
    proxy_id: uuid.UUID,
    payload: UpdateProxyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProxyPublic:
    row = db.get(Proxy, proxy_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy not found")

    if payload.scheme is not None:
        row.scheme = _normalize_scheme(payload.scheme)
    if payload.host is not None:
        row.host = payload.host.strip()
    if payload.port is not None:
        row.port = int(payload.port)
    if payload.country is not None:
        row.country = payload.country.strip().upper()[:2] if payload.country.strip() else None
    if payload.enabled is not None:
        row.enabled = bool(payload.enabled)
    if payload.weight is not None:
        row.weight = int(payload.weight)

    if payload.username is not None or payload.password is not None:
        _require_encryption_key()
        try:
            current = decrypt_json(row.auth_encrypted)
        except Exception:
            current = {}
        username = payload.username if payload.username is not None else current.get("username")
        password = payload.password if payload.password is not None else current.get("password")
        row.auth_encrypted = encrypt_json({"username": username, "password": password})

    db.add(row)
    db.commit()
    db.refresh(row)
    return ProxyPublic.model_validate(row, from_attributes=True)


@router.delete("/proxies/{proxy_id}")
def delete_proxy(
    proxy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(Proxy, proxy_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/proxies/{proxy_id}/check")
def check_proxy(
    proxy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_encryption_key()
    if settings.browser_cluster_mode.strip().lower() != "remote":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proxy check requires BROWSER_CLUSTER_MODE=remote")
    row = db.get(Proxy, proxy_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy not found")

    try:
        auth = decrypt_json(row.auth_encrypted)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to decrypt proxy credentials") from None

    server = f"{str(row.scheme).strip().lower()}://{row.host}:{int(row.port)}"
    proxy: dict = {"server": server}
    username = str(auth.get("username") or "").strip()
    password = str(auth.get("password") or "").strip()
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password

    storage_state = {"cookies": [], "origins": []}
    result = browser_cluster.execute_action(
        platform_key="x",
        action_type="proxy_check",
        storage_state=storage_state,
        target_url=None,
        target_external_id=None,
        bandwidth_mode="eco",
        action_params={},
        fingerprint_profile={},
        proxy=proxy,
    )

    status_value = str(result.get("status") or "failed")
    error_code = str(result.get("error_code")) if result.get("error_code") else None
    row.last_checked_at = utc_now()
    row.last_error_code = error_code
    if status_value == "succeeded":
        row.consecutive_failures = 0
    elif error_code == "PROXY_FAILED":
        row.consecutive_failures = int(row.consecutive_failures or 0) + 1
        if row.consecutive_failures >= 3:
            row.enabled = False
    db.add(row)
    db.commit()

    return {"status": status_value, "error_code": error_code, "current_url": result.get("current_url"), "ok": status_value == "succeeded"}
