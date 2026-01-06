from __future__ import annotations

import threading
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import encrypt_json
from app.db.session import SessionLocal
from app.models.credential import Credential
from app.models.login_session import LoginSession
from app.models.social_account import SocialAccount
from app.services.browser_cluster import browser_cluster
from app.utils.time import ensure_utc, utc_now

_POLL_INTERVAL_SECONDS = 3


def start_auto_capture(login_session_id: uuid.UUID) -> None:
    if not settings.login_session_auto_capture:
        return
    if settings.credential_encryption_key is None or not settings.credential_encryption_key.strip():
        return

    t = threading.Thread(target=_run, args=(login_session_id,), daemon=True)
    t.start()


def _run(login_session_id: uuid.UUID) -> None:
    while True:
        row = _get_session(login_session_id)
        if row is None:
            return

        now = utc_now()
        if row.status in {"succeeded", "failed", "expired", "canceled"}:
            return

        if ensure_utc(row.expires_at) <= now:
            _set_status(login_session_id, "expired")
            try:
                browser_cluster.stop_login_session(login_session_id=login_session_id)
            except Exception:
                pass
            return

        try:
            logged_in = browser_cluster.is_logged_in(login_session_id=login_session_id)
        except KeyError:
            return
        except Exception:
            time.sleep(_POLL_INTERVAL_SECONDS)
            continue

        if not logged_in:
            time.sleep(_POLL_INTERVAL_SECONDS)
            continue

        _finalize(login_session_id)
        return


def _get_session(login_session_id: uuid.UUID) -> LoginSession | None:
    with SessionLocal() as db:
        return db.get(LoginSession, login_session_id)


def _set_status(login_session_id: uuid.UUID, status_value: str) -> None:
    with SessionLocal() as db:
        row = db.get(LoginSession, login_session_id)
        if row is None:
            return
        row.status = status_value
        db.add(row)
        db.commit()


def _finalize(login_session_id: uuid.UUID) -> None:
    try:
        storage_state = browser_cluster.export_storage_state(login_session_id=login_session_id)
        encrypted_blob = encrypt_json(storage_state)
    except Exception:
        _set_status(login_session_id, "failed")
        try:
            browser_cluster.stop_login_session(login_session_id=login_session_id)
        except Exception:
            pass
        return

    with SessionLocal() as db:
        row = db.get(LoginSession, login_session_id)
        if row is None:
            return
        if row.status in {"succeeded", "expired", "canceled"}:
            return

        row.status = "capturing"
        db.add(row)
        db.commit()
        db.refresh(row)

        _upsert_credential(db, row, encrypted_blob)
        _mark_account_healthy(db, row.social_account_id)

        row.status = "succeeded"
        db.add(row)
        db.commit()

    try:
        browser_cluster.stop_login_session(login_session_id=login_session_id)
    except Exception:
        pass


def _upsert_credential(db: Session, login_session: LoginSession, encrypted_blob: bytes) -> None:
    credential = db.scalar(
        select(Credential).where(
            Credential.workspace_id == login_session.workspace_id,
            Credential.social_account_id == login_session.social_account_id,
            Credential.credential_type == "storage_state",
        )
    )
    now = utc_now()
    if credential is None:
        credential = Credential(
            workspace_id=login_session.workspace_id,
            social_account_id=login_session.social_account_id,
            credential_type="storage_state",
            encrypted_blob=encrypted_blob,
            key_version=1,
            validated_at=now,
        )
        db.add(credential)
    else:
        credential.encrypted_blob = encrypted_blob
        credential.validated_at = now
        db.add(credential)
    db.commit()


def _mark_account_healthy(db: Session, social_account_id: uuid.UUID) -> None:
    account = db.get(SocialAccount, social_account_id)
    if account is None:
        return
    account.status = "healthy"
    account.last_health_check_at = utc_now()
    db.add(account)
    db.commit()

