from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.artifact import Artifact
from app.models.subscription import WorkspaceSubscription
from app.utils.time import utc_now


@celery_app.task(name="syncsocial.cleanup_artifacts")
def cleanup_artifacts() -> None:
    now = utc_now()
    base_dir = Path(settings.artifacts_dir)

    with SessionLocal() as db:
        subs = (
            db.scalars(
                select(WorkspaceSubscription).where(
                    WorkspaceSubscription.artifact_retention_days.is_not(None),
                    WorkspaceSubscription.artifact_retention_days > 0,
                )
            )
            .all()
        )
        if not subs:
            return

        for sub in subs:
            try:
                days = int(sub.artifact_retention_days or 0)
            except Exception:
                continue
            if days <= 0:
                continue

            cutoff = now - timedelta(days=days)
            while True:
                batch = (
                    db.scalars(
                        select(Artifact)
                        .where(Artifact.workspace_id == sub.workspace_id, Artifact.created_at < cutoff)
                        .order_by(Artifact.created_at.asc())
                        .limit(200)
                    )
                    .all()
                )
                if not batch:
                    break

                for artifact in batch:
                    try:
                        path = base_dir / str(artifact.storage_key)
                        if path.exists():
                            path.unlink()
                    except Exception:
                        pass
                    try:
                        db.delete(artifact)
                    except Exception:
                        pass

                db.commit()

