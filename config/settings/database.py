"""Database settings for AlgoBot."""

from .base import BASE_DIR
from .utils import env, env_bool

DATABASE_URL = env("DATABASE_URL", "")
USE_POSTGRES = env_bool("USE_POSTGRES", bool(DATABASE_URL))
POSTGRES_DB = env("POSTGRES_DB", "deriv_platform")
POSTGRES_USER = env("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = env("POSTGRES_PORT", "5432")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2" if USE_POSTGRES else "django.db.backends.sqlite3",
        "NAME": POSTGRES_DB if USE_POSTGRES else BASE_DIR / "db.sqlite3",
        "USER": POSTGRES_USER if USE_POSTGRES else "",
        "PASSWORD": POSTGRES_PASSWORD if USE_POSTGRES else "",
        "HOST": POSTGRES_HOST if USE_POSTGRES else "",
        "PORT": POSTGRES_PORT if USE_POSTGRES else "",
    }
}
