"""Cache settings for AlgoBot."""

from .utils import env, env_bool

REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")
USE_REDIS = env_bool("USE_REDIS", False)

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache" if USE_REDIS else "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": REDIS_URL if USE_REDIS else "unique-deriv-platform",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"} if USE_REDIS else {},
    }
}
