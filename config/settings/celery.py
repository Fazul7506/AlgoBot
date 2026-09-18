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
CELERY_BROKER_CONNECTION_RETRY = False
CELERY_BROKER_CONNECTION_MAX_RETRIES = 0
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = False

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

# Backfill jobs are long-running, idempotent broker-data ingestion tasks.  Keep
# them visible to Celery, acknowledge them after execution, and requeue them if
# a worker is lost.  This prevents a database row from remaining "queued" after
# the Redis delivery disappeared with a worker restart.
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ROUTES = {
    "apps.market_data.tasks.run_initial_candle_backfill": {
        "queue": "market_data_backfill",
        "priority": 0,
    },
    "apps.market_data.tasks.backfill_research_candles": {
        "queue": "market_data_backfill",
        "priority": 0,
    },
    "apps.market_data.tasks.reconcile_candle_backfill_runs": {
        "queue": "market_data_backfill",
        "priority": 0,
    },
}
CELERY_TASK_ANNOTATIONS = {
    "apps.market_data.tasks.run_initial_candle_backfill": {
        "acks_late": True,
        "reject_on_worker_lost": True,
        "track_started": True,
    },
    "apps.market_data.tasks.backfill_research_candles": {
        "acks_late": True,
        "reject_on_worker_lost": True,
        "track_started": True,
    },
    "apps.market_data.tasks.reconcile_candle_backfill_runs": {
        "track_started": True,
    },
}
# Do not let long market-data work reserve a pile of unrelated tasks ahead of
# it.  A single outstanding task per worker process also makes the durable
# backfill state match actual worker execution more closely.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
