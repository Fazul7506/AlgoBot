"""Celery settings for AlgoBot."""

from .cache import REDIS_URL
from .utils import env, env_bool

CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL)
USE_CELERY = env_bool("USE_CELERY", True)
