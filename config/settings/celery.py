"""Celery settings for AlgoBot.

The HTTP request path must never wait on Redis long enough to become a browser
request timeout. Publishing is deliberately bounded and non-retrying for web
requests, while dedicated workers may reconnect normally.
"""

import os

from kombu import Queue

from .cache import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
from .utils import env_bool

USE_CELERY = env_bool("USE_CELERY", True)

CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_BROKER_POOL_LIMIT = max(1, int(os.environ.get("CELERY_BROKER_POOL_LIMIT", "1")))
CELERY_BROKER_CONNECTION_RETRY = env_bool("CELERY_WORKER_BROKER_RETRY", True)
CELERY_BROKER_CONNECTION_MAX_RETRIES = None if CELERY_BROKER_CONNECTION_RETRY else 0
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = env_bool(
    "CELERY_WORKER_RETRY_ON_STARTUP", True
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
    "max_connections": max(1, int(os.environ.get("CELERY_REDIS_MAX_CONNECTIONS", "2"))),
}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {
    "visibility_timeout": 4 * 60 * 60,
    "max_connections": max(1, int(os.environ.get("CELERY_REDIS_MAX_CONNECTIONS", "1"))),
}

# Long-running broker-data tasks expose STARTED state and are acknowledged only
# after execution. Worker loss therefore allows Celery to redeliver them.
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_WORKER_ENABLE_REMOTE_CONTROL = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100

# Declare every production queue explicitly. This prevents a broker-side queue
# from being created accidentally by a typo and makes the isolated market-data
# consumer contract inspectable during worker preflight.
CELERY_TASK_DEFAULT_QUEUE = "celery"
CELERY_TASK_CREATE_MISSING_QUEUES = False
CELERY_TASK_QUEUES = (
    # Bind each named queue to its own routing key. Without an explicit key,
    # Kombu can inherit the default ``celery`` routing key for both queues,
    # causing market-data messages to be delivered to the general worker too.
    Queue("celery", routing_key="celery"),
)

# Explicit imports make the production worker deterministic even if Django's
# autodiscovery behavior changes. This is especially important for the isolated
# market_data worker, which must register the task before consuming its queue.
CELERY_IMPORTS = (
    "apps.market_data.tasks",
)

CELERY_TASK_ROUTES = {
}

CELERY_TASK_ANNOTATIONS = {}
