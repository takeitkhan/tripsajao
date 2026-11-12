from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery("propsaas", broker=settings.redis_url, backend=settings.redis_url,
                    include=["app.workers.tasks"])
celery_app.conf.update(
    timezone="UTC", enable_utc=True, task_acks_late=True, worker_prefetch_multiplier=1,
    task_default_retry_delay=10,
    beat_schedule={
        # Safety net: keyspace notifications are fire-and-forget (missed if the listener is down).
        "sweep-expired-holds": {"task": "app.workers.tasks.sweep_expired_holds", "schedule": 60.0},
        "reconcile-partner-ledgers": {"task": "app.workers.tasks.reconcile_ledgers", "schedule": crontab(hour=2, minute=0)},
        "channel-statements": {"task": "app.workers.tasks.channel_statements", "schedule": crontab(hour=3, minute=0)},
    },
)
