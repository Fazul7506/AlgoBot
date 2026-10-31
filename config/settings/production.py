"""Production settings with fail-fast infrastructure and security validation."""

from .base import *  # noqa: F403,F401
from .utils import env, env_bool, env_list, validate_required_settings
from corsheaders.defaults import default_headers

DEBUG = False
# Render assigns a distinct *.onrender.com hostname to each service preview.
# Django's leading-dot syntax permits the apex and subdomains while retaining
# normal host validation for every other domain.
ALLOWED_HOSTS = [
    *env_list("ALLOWED_HOSTS", ["algobot.dpdns.org", "www.algobot.dpdns.org", "api.algobot.dpdns.org"]),
    ".onrender.com",
]
CSRF_TRUSTED_ORIGINS = [
    *env_list("CSRF_TRUSTED_ORIGINS", ["https://algobot.dpdns.org", "https://www.algobot.dpdns.org", "https://api.algobot.dpdns.org"]),
    "https://*.onrender.com",
]
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", ["https://algobot.dpdns.org", "https://www.algobot.dpdns.org", "https://api.algobot.dpdns.org"])
CORS_ALLOW_HEADERS = default_headers
CORS_ALLOW_CREDENTIALS = True
BASE_URL = env("BASE_URL", "https://algobot.dpdns.org").rstrip("/")
ALGO_API_BASE_URL = env("ALGO_API_BASE_URL", "https://api.algobot.dpdns.org").rstrip("/")

# Preview hosts are on a different registrable domain from algobot.dpdns.org.
# Use host-only cookies there; the production cookie domain would prevent the
# browser from sending the CSRF/session cookies to *.onrender.com.
RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", "").lower()
IS_RENDER_PREVIEW_HOST = RENDER_EXTERNAL_HOSTNAME.endswith(".onrender.com")

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
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_DOMAIN = None if IS_RENDER_PREVIEW_HOST else env("SESSION_COOKIE_DOMAIN", ".algobot.dpdns.org")
CSRF_COOKIE_DOMAIN = None if IS_RENDER_PREVIEW_HOST else env("CSRF_COOKIE_DOMAIN", ".algobot.dpdns.org")

WHITENOISE_MANIFEST_STRICT = False
USE_POSTGRES = True
USE_REDIS = True
# All production transactional email must use Brevo through Django Anymail.
# No SMTP fallback is supported: fail fast if the provider API key is absent.
EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
ANYMAIL = {"BREVO_API_KEY": BREVO_API_KEY}  # noqa: F405
if not BREVO_API_KEY:  # noqa: F405
    raise RuntimeError("Brevo Anymail backend requires BREVO_API_KEY.")

# DERIV_APP_ID is Deriv's numeric application ID; DERIV_OAUTH_CLIENT_ID
# is the OAuth client identifier. They are separate credentials and must not
# be compared for equality. Validate that each is configured independently below.

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

if PAYMENT_PROVIDER == "intasend":  # noqa: F405
    validate_required_settings(
        production=True,
        values={
            "INTASEND_PUBLIC_KEY": INTASEND_PUBLIC_KEY,  # noqa: F405
            "INTASEND_SECRET_KEY": INTASEND_SECRET_KEY,  # noqa: F405
            "INTASEND_WEBHOOK_CHALLENGE": INTASEND_WEBHOOK_CHALLENGE,  # noqa: F405
        },
    )
elif PAYMENT_PROVIDER == "pesapal":  # noqa: F405
    validate_required_settings(
        production=True,
        values={
            "PESAPAL_CONSUMER_KEY": PESAPAL_CONSUMER_KEY,  # noqa: F405
            "PESAPAL_CONSUMER_SECRET": PESAPAL_CONSUMER_SECRET,  # noqa: F405
            "PESAPAL_NOTIFICATION_ID": PESAPAL_NOTIFICATION_ID,  # noqa: F405
        },
    )

SENTRY_DSN = env("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
    )
