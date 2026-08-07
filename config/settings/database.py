"""Database settings for AlgoBot."""

from urllib.parse import urlparse

from .base import BASE_DIR
from .utils import env, env_bool

DATABASE_URL = env("DATABASE_URL", "")
USE_POSTGRES = env_bool("USE_POSTGRES", bool(DATABASE_URL))
POSTGRES_DB = env("POSTGRES_DB", "deriv_platform")
POSTGRES_USER = env("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", "")
POSTGRES_HOST = env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = env("POSTGRES_PORT", "5432")


def _postgres_from_url(database_url: str) -> dict[str, str]:
    parsed = urlparse(database_url)
    return {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
    }


def _postgres_from_parts() -> dict[str, str]:
    return {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": POSTGRES_DB,
        "USER": POSTGRES_USER,
        "PASSWORD": POSTGRES_PASSWORD,
        "HOST": POSTGRES_HOST,
        "PORT": POSTGRES_PORT,
    }


DATABASES = {
    "default": (
        _postgres_from_url(DATABASE_URL)
        if DATABASE_URL
        else _postgres_from_parts()
        if USE_POSTGRES
        else {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    )
}
