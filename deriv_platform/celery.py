import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deriv_platform.settings')

app = Celery('deriv_platform')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# AI learning loop. Broker adapters write canonical ticks/candles first; these
# jobs inspect that shared data store and train validated models from it.
app.conf.beat_schedule = {
    'ai-data-health-every-15-minutes': {
        'task': 'apps.ai_engine.tasks.check_ai_data_health',
        'schedule': crontab(minute='*/15'),
        'kwargs': {'timeframe': 'M1'},
    },
    'ai-training-every-6-hours': {
        'task': 'apps.ai_engine.tasks.scheduled_ai_training',
        'schedule': crontab(minute=15, hour='*/6'),
        'kwargs': {'timeframe': 'M1', 'min_accuracy': 0.52},
    },
    'ai-full-training-daily': {
        'task': 'apps.ai_engine.tasks.scheduled_ai_training',
        'schedule': crontab(minute=30, hour=2),
        'kwargs': {'timeframe': 'M1', 'min_accuracy': 0.52},
    },
}
