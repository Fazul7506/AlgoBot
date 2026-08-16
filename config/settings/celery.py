"""Celery settings for AlgoBot."""

from .cache import CELERY_BROKER_URL, CELERY_RESULT_BACKEND, USE_REDIS
from .utils import env_bool

# Keep these settings centralized in cache.py so managed Redis URLs loaded from
# .env are also used by Celery.  USE_CELERY remains independently configurable.
USE_CELERY = env_bool("USE_CELERY", True)
