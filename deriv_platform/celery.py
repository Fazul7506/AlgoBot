import os

from celery import Celery
from celery.signals import task_postrun, task_prerun
from django.db import close_old_connections
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

app = Celery("deriv_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@task_prerun.connect

def _close_stale_task_connections(*args, **kwargs):
    """Release stale Django DB connections before a long-running task."""
    close_old_connections()


@task_postrun.connect

def _close_task_connections(*args, **kwargs):
    """Release obsolete/failed DB connections after every Celery task."""
    close_old_connections()


app.conf.beat_schedule = {} if os.environ.get("CLOUDFLARE_SCHEDULER_ACTIVE", "").lower() == "true" else {
    "automation-due-schedules-every-30-seconds": {
        "task": "apps.automation.tasks.process_due_scheduled_tasks",
        "schedule": 30.0,
        "kwargs": {"limit": 100},
        "options": {"queue": "celery", "expires": 25},
    },
    "execution-queue-recovery-every-30-seconds": {
        "task": "apps.execution.process_execution_queue",
        "schedule": 30.0,
        "kwargs": {"batch_size": 10},
        # Do not let a slow execution cycle create an unbounded backlog of
        # database-heavy polling tasks. A fresh tick replaces an expired one.
        # The task also takes a distributed Redis lock, so execution remains
        # logically singleton even though the general worker handles other jobs.
        "options": {"queue": "celery", "expires": 25},
    },
    "ai-data-health-every-15-minutes": {
        "task": "apps.ai_engine.tasks.check_ai_data_health",
        "schedule": crontab(minute="*/15"),
        "kwargs": {"timeframe": "M1"},
    },
    "ai-model-degradation-every-15-minutes": {
        "task": "apps.ai_engine.tasks.check_model_degradation",
        "schedule": crontab(minute="*/15"),
    },
    "ai-resolve-predictions-every-5-minutes": {
        "task": "apps.ai_engine.tasks.resolve_prediction_outcomes",
        "schedule": crontab(minute="*/5"),
        "kwargs": {"timeframe": "M1", "horizon_candles": 1, "batch_size": 500},
    },
    "telegram-watchdog-every-minute": {
        "task": "apps.notifications.tasks.telegram_watchdog",
        "schedule": crontab(),
    },
    "telegram-recover-stuck-every-5-minutes": {
        "task": "apps.notifications.tasks.recover_stuck_notifications",
        "schedule": crontab(minute="*/5"),
    },
}
