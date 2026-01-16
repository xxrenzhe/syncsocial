from __future__ import annotations

import hashlib
import random
import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json
from app.models.proxy import Proxy
from app.models.proxy_pool import ProxyPool
from app.utils.time import ensure_utc, utc_now

_ALLOWED_POOL_STRATEGIES = {"hash", "random"}
_ALLOWED_SCHEMES = {"http", "https", "socks5"}
_COOLDOWN_BY_FAILURES: dict[int, timedelta] = {
    1: timedelta(seconds=90),
    2: timedelta(minutes=5),
}
_DEFAULT_COOLDOWN = timedelta(minutes=15)


@dataclass(frozen=True)
class SelectedProxy:
    proxy_id: uuid.UUID
    server: str
    username: str | None
    password: str | None

    def to_playwright_proxy(self) -> dict:
        payload: dict = {"server": self.server}
        if self.username:
            payload["username"] = self.username
        if self.password:
            payload["password"] = self.password
        return payload


def select_proxy_for_account(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    pool_id: uuid.UUID,
) -> dict:
    selected = select_proxy_for_account_with_id(db, workspace_id=workspace_id, account_id=account_id, pool_id=pool_id)
    return selected.to_playwright_proxy()


def select_proxy_for_account_with_id(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    pool_id: uuid.UUID,
    attempt: int = 0,
) -> SelectedProxy:
    pool = db.get(ProxyPool, pool_id)
    if pool is None or pool.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid proxy_pool_id")

    strategy = str(pool.strategy or "").strip().lower() or "hash"
    if strategy not in _ALLOWED_POOL_STRATEGIES:
        strategy = "hash"

    all_proxies = db.scalars(
        select(Proxy)
        .where(
            Proxy.workspace_id == workspace_id,
            Proxy.pool_id == pool_id,
            Proxy.enabled.is_(True),
        )
        .order_by(Proxy.created_at.asc())
    ).all()
    if not all_proxies:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No enabled proxies in pool")

    now = utc_now()
    proxies = [proxy for proxy in all_proxies if not _is_proxy_in_cooldown(proxy, now)]
    if not proxies:
        proxies = all_proxies

    chosen: Proxy
    if strategy == "random":
        weights = [max(1, int(getattr(p, "weight", 1) or 1)) for p in proxies]
        seed = hashlib.sha256(f"{account_id}:{attempt}".encode("utf-8")).digest()
        rnd = random.Random(int.from_bytes(seed[:8], "big"))
        chosen = rnd.choices(proxies, weights=weights, k=1)[0]
    else:
        digest = hashlib.sha256(str(account_id).encode("utf-8")).digest()
        offset = int(attempt) if isinstance(attempt, int) and attempt > 0 else 0
        index = (int.from_bytes(digest[:4], "big") + offset) % len(proxies)
        chosen = proxies[index]

    scheme = str(chosen.scheme or "http").strip().lower()
    if scheme not in _ALLOWED_SCHEMES:
        scheme = "http"

    server = f"{scheme}://{chosen.host}:{int(chosen.port)}"

    try:
        auth = decrypt_json(chosen.auth_encrypted)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to decrypt proxy credentials") from exc

    username = str(auth.get("username") or "").strip() or None
    password = str(auth.get("password") or "").strip() or None
    return SelectedProxy(proxy_id=chosen.id, server=server, username=username, password=password)


def _is_proxy_in_cooldown(proxy: Proxy, now) -> bool:
    failures = int(getattr(proxy, "consecutive_failures", 0) or 0)
    if failures <= 0:
        return False
    last_checked_at = getattr(proxy, "last_checked_at", None)
    if last_checked_at is None:
        return False

    cooldown = _COOLDOWN_BY_FAILURES.get(failures, _DEFAULT_COOLDOWN)
    return ensure_utc(last_checked_at) > ensure_utc(now) - cooldown
