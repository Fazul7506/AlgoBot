"""Celery settings for AlgoBot.

The HTTP request path must never wait on Redis long enough to become a browser
request timeout. Publishing is therefore deliberately bounded and non-retrying.
Workers themselves may reconnect normally; the web process must fail fast when
there is no reachable broker.
"""

from .cache import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
from .utils import env_bool

USE_CELERY = env_bool("USE_CELERY", True)

# Keep broker/result URLs centralized in cache.py so managed Redis configuration
# is shared by Django, Channels and Celery.
CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_BROKER_CONNECTION_RETRY = env_bool("CELERY_WORKER_BROKER_RETRY", False)
CELERY_BROKER_CONNECTION_MAX_RETRIES = None if CELERY_BROKER_CONNECTION_RETRY else 0
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = env_bool("CELERY_WORKER_RETRY_ON_STARTUP", False)

# A failed publish is a failed queue operation, not a reason to hold an HTTP
# request open while Celery retries a dead Redis connection.
CELERY_TASK_PUBLISH_RETRY = False
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 0,
    "timeout": 3,
}

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": 3,
    "socket_timeout": 3,
}

CELERY_BROKER_URL = CELERY_BROKER_URL
CELERY_RESULT_BACKEND = CELERY_RESULT_BACKEND


# Long-running market backfills need visible STARTED state and conservative
# prefetching so one heavy job cannot hide all other queued work.
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100


# Historical broker ingestion is isolated so its deliberate rate limiting cannot
# starve execution, notifications, or other default-queue tasks.
CELERY_TASK_ROUTES = {
    "apps.market_data.tasks.backfill_research_candles": {"queue": "market_data"},
    "apps.market_data.tasks.run_initial_candle_backfill": {"queue": "market_data"},
}
