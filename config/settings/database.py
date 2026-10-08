"""Database settings for AlgoBot."""

from urllib.parse import urlparse

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


def _database_conn_max_age(database_url):
    """Choose a safe Django connection lifetime for the configured database."""
    configured = env("DB_CONN_MAX_AGE", "").strip()
    if configured:
        try:
            value = int(configured)
        except ValueError as exc:
            raise ValueError("DB_CONN_MAX_AGE must be an integer number of seconds.") from exc
        if value < 0:
            raise ValueError("DB_CONN_MAX_AGE must be >= 0.")
        return value

    # Supavisor session-mode connections (port 5432) are persistent client
    # sessions. With several Render web/worker processes, Django's default
    # 600-second persistence can hold idle pooler sessions long enough to
    # exhaust the shared pool. Releasing the client connection at request/task
    # boundaries lets Supavisor recycle the underlying database connection.
    hostname = (urlparse(database_url).hostname or "").lower()
    if hostname.endswith(".pooler.supabase.com"):
        return 0

    return 600


if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=_database_conn_max_age(DATABASE_URL),
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
