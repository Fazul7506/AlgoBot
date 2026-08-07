"""Production settings for AlgoBot."""

from .development import *  # noqa: F403
from .utils import validate_required_settings

DEBUG = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

validate_required_settings(
    production=True,
    values={
        "SECRET_KEY": SECRET_KEY,  # noqa: F405
        "ALLOWED_HOSTS": ",".join(ALLOWED_HOSTS),  # noqa: F405
        "DATABASE_URL or POSTGRES_*": DATABASE_URL or (POSTGRES_DB and POSTGRES_USER and POSTGRES_PASSWORD and POSTGRES_HOST),  # noqa: F405
        "REDIS_URL": REDIS_URL,  # noqa: F405
        "BASE_URL": BASE_URL,  # noqa: F405
        "DERIV_APP_ID": DERIV_APP_ID,  # noqa: F405
        "DERIV_REDIRECT_URI": DERIV_REDIRECT_URI,  # noqa: F405
    },
)
