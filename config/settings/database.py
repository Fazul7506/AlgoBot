"""Database settings for AlgoBot."""

import dj_database_url

from .base import BASE_DIR
from .utils import env, env_bool

DATABASE_URL = env("DATABASE_URL", "")
USE_POSTGRES = env_bool("USE_POSTGRES", bool(DATABASE_URL))

POSTGRES_DB = env("POSTGRES_DB", "deriv_platform")
POSTGRES_USER = env("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", "")
POSTGRES_HOST = env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = env("POSTGRES_PORT", "5432")


if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
elif USE_POSTGRES:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": POSTGRES_DB,
            "USER": POSTGRES_USER,
            "PASSWORD": POSTGRES_PASSWORD,
            "HOST": POSTGRES_HOST,
            "PORT": POSTGRES_PORT,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
