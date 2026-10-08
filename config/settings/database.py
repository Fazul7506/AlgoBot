"""Database settings for AlgoBot."""

import os
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

    # AlgoBot runs ASGI on Render. Keep Django's per-request connection lifetime
    # at zero so database connections are returned promptly; production uses the
    # explicit psycopg connection pool below to cap concurrent client sessions.
    hostname = (urlparse(database_url).hostname or "").lower()
    if hostname.endswith(".pooler.supabase.com"):
        return 0

    return 600


def _database_pool_options(database_url):
    """Return bounded psycopg pool settings for production ASGI workloads."""
    enabled = env_bool("DB_CONNECTION_POOL_ENABLED", os.getenv("DJANGO_ENV", "").lower() == "production")
    if not enabled:
        return {}

    hostname = (urlparse(database_url).hostname or "").lower()
    if not hostname:
        return {}

    try:
        min_size = int(env("DB_POOL_MIN_SIZE", "1"))
        max_size = int(env("DB_POOL_MAX_SIZE", "3"))
        max_lifetime = int(env("DB_POOL_MAX_LIFETIME", "1800"))
        timeout = int(env("DB_POOL_TIMEOUT", "10"))
    except ValueError as exc:
        raise ValueError(
            "DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE, and DB_POOL_MAX_LIFETIME must be integers."
        ) from exc

    if min_size < 0:
        raise ValueError("DB_POOL_MIN_SIZE must be >= 0.")
    if max_size < 1 or max_size < min_size:
        raise ValueError("DB_POOL_MAX_SIZE must be >= DB_POOL_MIN_SIZE and >= 1.")
    if max_lifetime <= 0:
        raise ValueError("DB_POOL_MAX_LIFETIME must be > 0.")
    if timeout <= 0:
        raise ValueError("DB_POOL_TIMEOUT must be > 0.")

    # Django 5.2+ supports psycopg's built-in pool. A small explicit maximum is
    # important for Supabase session-mode pooling, where the client pool size
    # is the effective per-role connection ceiling. Keep server-side cursors
    # disabled so the same configuration remains safe if the URL is later
    # moved to Supabase transaction pooling.
    return {
        "pool": {
            "min_size": min_size,
            "max_size": max_size,
            "max_lifetime": max_lifetime,
            "timeout": timeout,
        },
        "server_side_binding": False,
    }


if DATABASE_URL:
    database_config = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=_database_conn_max_age(DATABASE_URL),
        ssl_require=True,
    )
    pool_options = _database_pool_options(DATABASE_URL)
    if pool_options:
        disable_server_side_cursors = pool_options.pop("DISABLE_SERVER_SIDE_CURSORS", False)
        database_config["OPTIONS"] = {
            **database_config.get("OPTIONS", {}),
            **pool_options,
        }
        if disable_server_side_cursors:
            database_config["DISABLE_SERVER_SIDE_CURSORS"] = True
    DATABASES = {"default": database_config}
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
