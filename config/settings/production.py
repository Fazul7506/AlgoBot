"""Production settings with fail-fast infrastructure and security validation."""

from .base import *  # noqa: F403,F401
from .utils import env, env_bool, env_list, validate_required_settings

DEBUG = False
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["algobot.dpdns.org", "api.algobot.dpdns.org"])
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", ["https://algobot.dpdns.org"])
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", ["https://algobot.dpdns.org"])
CORS_ALLOW_CREDENTIALS = True
BASE_URL = env("BASE_URL", "https://algobot.dpdns.org").rstrip("/")
ALGO_API_BASE_URL = env("ALGO_API_BASE_URL", "https://api.algobot.dpdns.org").rstrip("/")

# Render terminates TLS at its edge and forwards requests internally over HTTP.
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", True)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN", ".algobot.dpdns.org")
CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN", ".algobot.dpdns.org")

WHITENOISE_MANIFEST_STRICT = False
USE_POSTGRES = True
USE_REDIS = True
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")

# OAuth and API authentication must use one canonical Deriv application ID.
if DERIV_OAUTH_CLIENT_ID and DERIV_APP_ID and DERIV_APP_ID != DERIV_OAUTH_CLIENT_ID:  # noqa: F405
    raise RuntimeError("DERIV_APP_ID must match DERIV_OAUTH_CLIENT_ID in production.")

validate_required_settings(
    production=True,
    values={
        "SECRET_KEY": SECRET_KEY,  # noqa: F405
        "ALLOWED_HOSTS": ",".join(ALLOWED_HOSTS),
        "CSRF_TRUSTED_ORIGINS": ",".join(CSRF_TRUSTED_ORIGINS),
        "BASE_URL": BASE_URL,
        "REDIS_URL": REDIS_URL,  # noqa: F405
        "DERIV_OAUTH_CLIENT_ID": DERIV_OAUTH_CLIENT_ID,  # noqa: F405
        "DERIV_APP_ID": DERIV_APP_ID,  # noqa: F405
        "DERIV_REDIRECT_URI": DERIV_REDIRECT_URI,  # noqa: F405
        "DATABASE_URL or POSTGRES_*": DATABASE_URL or (
            POSTGRES_DB and POSTGRES_USER and POSTGRES_PASSWORD and POSTGRES_HOST
        ),  # noqa: F405
    },
)

if SECRET_KEY in {"django-insecure-local-development-only", "change-me"}:
    raise RuntimeError("Production SECRET_KEY must be explicitly configured.")

SENTRY_DSN = env("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
    )
