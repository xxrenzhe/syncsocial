from __future__ import annotations

import uuid

from sqlalchemy import update

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.account_run import AccountRun
from app.utils.time import utc_now


@celery_app.task(name="syncsocial.tick_retries")
def tick_retries() -> int:
    now = utc_now()
    with SessionLocal() as db:
        stmt = (
            update(AccountRun)
            .where(AccountRun.status == "retry_waiting", AccountRun.next_retry_at.is_not(None), AccountRun.next_retry_at <= now)
            .values(status="queued")
            .returning(AccountRun.id)
        )
        ids = db.execute(stmt).scalars().all()
        db.commit()

    enqueued = 0
    for account_run_id in ids:
        try:
            celery_app.send_task("syncsocial.execute_account_run", args=[str(uuid.UUID(str(account_run_id)))])
            enqueued += 1
        except Exception:
            continue
    return enqueued

