"""Django base settings shared across environments.

Environment-specific modules (notably ``production.py``) override security and
infrastructure settings. Keep this module safe for local development while
never providing a production-usable secret fallback.
"""

import os
from datetime import timedelta
from pathlib import Path

from config.settings.utils import get_bool_env, get_list_env

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRET_KEY = os.getenv("SECRET_KEY", os.getenv("DJANGO_SECRET_KEY", "django-insecure-local-development-only"))
DEBUG = get_bool_env("DEBUG", get_bool_env("DJANGO_DEBUG", True))
ALLOW_LIVE_TRADING = get_bool_env("ALLOW_LIVE_TRADING", False)
ENABLE_BROKER_ACCOUNT_SWITCH = get_bool_env("ENABLE_BROKER_ACCOUNT_SWITCH", True)

ALLOWED_HOSTS = get_list_env("ALLOWED_HOSTS", ["127.0.0.1", "localhost", "testserver", "algobot.dpdns.org", "www.algobot.dpdns.org", "api.algobot.dpdns.org"])
TIME_ZONE = os.getenv("TIME_ZONE", "UTC")
LANGUAGE_CODE = "en-us"
USE_I18N = True
USE_TZ = True
SECURE_SSL_REDIRECT = get_bool_env("SECURE_SSL_REDIRECT", False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = get_bool_env("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = get_bool_env("CSRF_COOKIE_SECURE", False)
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_HTTPONLY = False
CSRF_TRUSTED_ORIGINS = get_list_env("CSRF_TRUSTED_ORIGINS", ["https://algobot.dpdns.org", "https://www.algobot.dpdns.org", "https://api.algobot.dpdns.org"] if os.getenv("ALGO_API_BASE_URL") else [])

INSTALLED_APPS = [
    "daphne", "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "rest_framework_simplejwt", "corsheaders", "django_filters", "core",
    "apps.admin_portal", "apps.ai_engine", "apps.alerts", "apps.analysis", "apps.analytics",
    "apps.audit", "apps.automation", "apps.backtesting", "apps.brokers", "apps.community",
    "apps.contracts", "apps.copy_trading", "apps.dashboard", "apps.deployment", "apps.deriv",
    "apps.developer", "apps.developer_api", "apps.enterprise", "apps.execution", "apps.feature_flags",
    "apps.feature_store", "apps.followers", "apps.health", "apps.indicators", "apps.journal",
    "apps.leaderboards", "apps.licensing", "apps.logging_system", "apps.market_data", "apps.marketplace",
    "apps.metrics", "apps.ml_models", "apps.monitoring", "apps.notifications", "apps.observability",
    "apps.optimization", "apps.organizations", "apps.paper_trading", "apps.portfolio", "apps.providers",
    "apps.rbac", "apps.referrals", "apps.reports", "apps.risk", "apps.signals", "apps.simulation",
    "apps.smart_money", "apps.strategies", "apps.subscriptions", "apps.support", "apps.tenants",
    "apps.trading", "apps.training", "apps.usage", "apps.workspace", "trading.apps.TradingConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware", "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "core.middleware.csrf.APIAwareCsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "apps.developer.middleware.DeveloperAPIMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.audit_middleware.AuditMiddleware", "core.middleware.plan_entitlement_middleware.PlanEntitlementMiddleware",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "core.api_authentication.BrowserSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend", "rest_framework.filters.SearchFilter", "rest_framework.filters.OrderingFilter"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "100/hour", "user": "1000/hour"},
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1), "REFRESH_TOKEN_LIFETIME": timedelta(days=7), "ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True, "ALGORITHM": "HS256", "SIGNING_KEY": SECRET_KEY,
}

CORS_ALLOWED_ORIGINS = get_list_env(
    "CORS_ALLOWED_ORIGINS",
    ["http://127.0.0.1:3000", "http://localhost:3000", "http://127.0.0.1:8000", "http://localhost:8000", "https://algobot.dpdns.org", "https://www.algobot.dpdns.org"]
    if os.getenv("ALGO_API_BASE_URL")
    else ["http://127.0.0.1:3000", "http://localhost:3000", "http://127.0.0.1:8000", "http://localhost:8000"],
)
CORS_ALLOW_CREDENTIALS = True

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug", "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages",
    ]},
}]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]