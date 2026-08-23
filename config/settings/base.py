"""Base Django settings shared by all AlgoBot environments."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from .utils import env, env_bool, env_list

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = env("SECRET_KEY", env("DJANGO_SECRET_KEY", ""))
DEBUG = env_bool("DEBUG", env_bool("DJANGO_DEBUG", False))
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["127.0.0.1", "localhost", "testserver"])

DJANGO_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = ["rest_framework", "rest_framework_simplejwt", "rest_framework_simplejwt.token_blacklist"]
LOCAL_APPS = [
    "anymail", "core", "trading", "apps.deriv", "apps.market_data", "apps.indicators",
    "apps.analysis", "apps.execution", "apps.trading", "apps.contracts", "apps.strategies", "apps.smart_money",
    "apps.risk", "apps.ai_engine", "apps.ml_models", "apps.feature_store", "apps.training", "apps.monitoring",
    "apps.analytics", "apps.logging_system", "apps.alerts", "apps.audit", "apps.health", "apps.metrics",
    "apps.backtesting", "apps.paper_trading", "apps.optimization", "apps.simulation", "apps.portfolio",
    "apps.brokers", "apps.tenants", "apps.copy_trading", "apps.automation", "apps.notifications",
    "apps.developer", "apps.deployment", "apps.observability", "apps.enterprise",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.security.RejectMalformedPathMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.developer.middleware.DeveloperAPIMiddleware",
    "core.middleware.audit_middleware.AuditMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "deriv_platform.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "deriv_platform.wsgi.application"
ASGI_APPLICATION = "deriv_platform.asgi.application"

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Africa/Nairobi")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

BASE_URL = env("BASE_URL", "").rstrip("/")
DERIV_OAUTH_CLIENT_ID = env("DERIV_OAUTH_CLIENT_ID", "")
DERIV_APP_ID = env("DERIV_APP_ID", DERIV_OAUTH_CLIENT_ID)
DERIV_OAUTH_CLIENT_SECRET = env("DERIV_OAUTH_CLIENT_SECRET", "")
DERIV_OAUTH_SCOPE = env("DERIV_OAUTH_SCOPE", "trade")
DERIV_LEGACY_APP_ID = env("DERIV_LEGACY_APP_ID", "")
DERIV_ENABLE_LEGACY_APP_ROUTING = env_bool("DERIV_ENABLE_LEGACY_APP_ROUTING", False)
DERIV_REDIRECT_URI = env("DERIV_REDIRECT_URI", f"{BASE_URL}/callback/" if BASE_URL else "")
DERIV_API_BASE_URL = env("DERIV_API_BASE_URL", "https://api.derivws.com")
DERIV_PUBLIC_WS_URL = env("DERIV_PUBLIC_WS_URL", "wss://api.derivws.com/trading/v1/options/ws/public")
DERIV_AUTH_WS_BASE_URL = env("DERIV_AUTH_WS_BASE_URL", "wss://api.derivws.com/trading/v1/options/ws")
DERIV_OPTIONS_ACCOUNTS_URL = env("DERIV_OPTIONS_ACCOUNTS_URL", f"{DERIV_API_BASE_URL}/trading/v1/options/accounts")
DERIV_API_TOKEN = env("DERIV_API_TOKEN", "")
ALLOW_LIVE_TRADING = env_bool("ALLOW_LIVE_TRADING", False)
OPENAI_API_KEY = env("OPENAI_API_KEY", "")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ALGORITHM": "HS256", "SIGNING_KEY": SECRET_KEY,
    "ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True,
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "/brokers/connect/?broker=deriv"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

DEVELOPER_API_RATE_LIMIT = int(env("DEVELOPER_API_RATE_LIMIT", "60"))
DEVELOPER_API_RATE_WINDOW = int(env("DEVELOPER_API_RATE_WINDOW", "60"))
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
ANYMAIL = {"BREVO_API_KEY": env("BREVO_API_KEY", "")}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@algobot.dpdns.org")
SERVER_EMAIL = env("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", "Lax")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
