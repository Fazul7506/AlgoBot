import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "deriv_platform.settings")

app = Celery("deriv_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "execution-queue-every-2-seconds": {"task": "apps.execution.process_execution_queue", "schedule": 2.0, "kwargs": {"batch_size": 10}},
    "ai-data-health-every-15-minutes": {"task": "apps.ai_engine.tasks.check_ai_data_health", "schedule": crontab(minute="*/15"), "kwargs": {"timeframe": "M1"}},
    "ai-resolve-predictions-every-5-minutes": {"task": "apps.ai_engine.tasks.resolve_prediction_outcomes", "schedule": crontab(minute="*/5"), "kwargs": {"timeframe": "M1", "horizon_candles": 1, "batch_size": 500}},
    "ai-training-every-6-hours": {"task": "apps.ai_engine.tasks.scheduled_ai_training", "schedule": crontab(minute=15, hour="*/6"), "kwargs": {"timeframe": "M1", "min_accuracy": 0.52}},
    "ai-full-training-daily": {"task": "apps.ai_engine.tasks.scheduled_ai_training", "schedule": crontab(minute=30, hour=2), "kwargs": {"timeframe": "M1", "min_accuracy": 0.52}},
    "telegram-watchdog-every-minute": {"task": "apps.notifications.tasks.telegram_watchdog", "schedule": crontab()},
    "telegram-recover-stuck-every-5-minutes": {"task": "apps.notifications.tasks.recover_stuck_notifications", "schedule": crontab(minute="*/5")},
}
