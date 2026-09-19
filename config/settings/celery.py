"""Celery settings for AlgoBot.

The HTTP request path must never wait on Redis long enough to become a browser
request timeout. Publishing is deliberately bounded and non-retrying for web
requests, while dedicated workers may reconnect normally.
"""

from .cache import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
from .utils import env_bool

USE_CELERY = env_bool("USE_CELERY", True)

CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_BROKER_CONNECTION_RETRY = env_bool("CELERY_WORKER_BROKER_RETRY", False)
CELERY_BROKER_CONNECTION_MAX_RETRIES = None if CELERY_BROKER_CONNECTION_RETRY else 0
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = env_bool(
    "CELERY_WORKER_RETRY_ON_STARTUP", False
)

# A failed web publish is a failed queue operation, not a reason to hold an HTTP
# request open while Redis is unavailable.
CELERY_TASK_PUBLISH_RETRY = False
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 0,
    "timeout": 3,
}

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": 3,
    "socket_timeout": 3,
    # Initial broker history can be long-running. Keep Redis from redelivering
    # a still-running late-ack task before its durable heartbeat/recovery logic
    # can make a decision.
    "visibility_timeout": 4 * 60 * 60,
}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {
    "visibility_timeout": 4 * 60 * 60,
}

CELERY_BROKER_URL = CELERY_BROKER_URL
CELERY_RESULT_BACKEND = CELERY_RESULT_BACKEND

# Long-running broker-data tasks expose STARTED state and are acknowledged only
# after execution. Worker loss therefore allows Celery to redeliver them.
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SEND_SENT_EVENT = True
# Emit worker/task lifecycle events so delivery and STARTED state are observable.
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_WORKER_ENABLE_REMOTE_CONTROL = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100

CELERY_TASK_ROUTES = {
    "apps.market_data.tasks.backfill_research_candles": {"queue": "market_data"},
    "apps.market_data.tasks.run_initial_candle_backfill": {"queue": "market_data"},
    # Recovery/observability must not share the single-consumer market-data queue.
    # If the long-running backfill is stalled there, a recovery task on that same
    # queue could never execute. The general worker consumes the default celery queue.
    "apps.market_data.tasks.reconcile_candle_backfill_runs": {"queue": "celery"},
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
