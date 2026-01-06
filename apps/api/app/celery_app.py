from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery("syncsocial", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_always_eager = settings.celery_task_always_eager
celery_app.autodiscover_tasks(["app"])

celery_app.conf.beat_schedule = {
    "syncsocial-tick-schedules": {
        "task": "syncsocial.tick_schedules",
        "schedule": 30.0,
    },
    "syncsocial-cleanup-artifacts": {
        "task": "syncsocial.cleanup_artifacts",
        "schedule": 6 * 60 * 60.0,
    },
}
