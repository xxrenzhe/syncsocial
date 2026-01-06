from __future__ import annotations

import uuid

from sqlalchemy import select

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.account_run import AccountRun
from app.models.action import Action
from app.models.credential import Credential
from app.models.run import Run
from app.models.social_account import SocialAccount
from app.utils.time import utc_now


@celery_app.task(name="syncsocial.execute_account_run")
def execute_account_run(account_run_id: str) -> None:
    account_run_uuid = uuid.UUID(account_run_id)
    now = utc_now()

    with SessionLocal() as db:
        account_run = db.get(AccountRun, account_run_uuid)
        if account_run is None:
            return
        if account_run.status not in {"queued", "retry_waiting"}:
            return

        run = db.get(Run, account_run.run_id)
        if run is None:
            return

        account_run.status = "running"
        account_run.started_at = now
        db.add(account_run)

        if run.status == "queued":
            run.status = "running"
            run.started_at = now
            db.add(run)

        db.commit()

        account = db.get(SocialAccount, account_run.social_account_id)
        if account is None:
            _fail_account_run(db, account_run, run, error_code="ACCOUNT_NOT_FOUND")
            return

        idempotency_key = f"{account_run.workspace_id}:{account.id}:health_check:{run.id}"
        action = Action(
            workspace_id=account_run.workspace_id,
            account_run_id=account_run.id,
            action_type="health_check",
            platform_key=account.platform_key,
            target_external_id=None,
            target_url=None,
            idempotency_key=idempotency_key,
            status="running",
            error_code=None,
            metadata_={},
            started_at=utc_now(),
        )
        db.add(action)
        db.commit()
        db.refresh(action)

        credential = db.scalar(
            select(Credential).where(
                Credential.workspace_id == account_run.workspace_id,
                Credential.social_account_id == account.id,
                Credential.credential_type == "storage_state",
            )
        )

        if account.status != "healthy" or credential is None:
            action.status = "failed"
            action.error_code = "AUTH_REQUIRED"
            action.finished_at = utc_now()
            db.add(action)
            db.commit()
            _fail_account_run(db, account_run, run, error_code="AUTH_REQUIRED")
            return

        action.status = "succeeded"
        action.finished_at = utc_now()
        db.add(action)
        db.commit()

        account_run.status = "succeeded"
        account_run.finished_at = utc_now()
        db.add(account_run)
        db.commit()

        _finalize_run_if_done(db, run.id)


def _fail_account_run(db, account_run: AccountRun, run: Run, *, error_code: str) -> None:
    account_run.status = "failed"
    account_run.error_code = error_code
    account_run.finished_at = utc_now()
    db.add(account_run)
    if run.status == "queued":
        run.status = "running"
        run.started_at = utc_now()
        db.add(run)
    db.commit()
    _finalize_run_if_done(db, run.id)


def _finalize_run_if_done(db, run_id: uuid.UUID) -> None:
    run = db.get(Run, run_id)
    if run is None:
        return

    account_runs = db.scalars(select(AccountRun).where(AccountRun.run_id == run.id)).all()
    if not account_runs:
        run.status = "succeeded"
        run.finished_at = utc_now()
        db.add(run)
        db.commit()
        return

    if any(ar.status in {"queued", "running", "retry_waiting"} for ar in account_runs):
        return

    if any(ar.status == "failed" for ar in account_runs):
        run.status = "failed"
    else:
        run.status = "succeeded"
    run.finished_at = utc_now()
    db.add(run)
    db.commit()

