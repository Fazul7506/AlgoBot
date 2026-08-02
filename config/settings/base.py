"""Base Django settings shared by all AlgoBot environments."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from .utils import env, env_bool, env_list

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = env("SECRET_KEY", env("DJANGO_SECRET_KEY", "django-insecure-local-development-only"))
DEBUG = env_bool("DEBUG", env_bool("DJANGO_DEBUG", True))
ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    ["giblet-squeegee-flatly.ngrok-free.dev", "127.0.0.1", "localhost", "testserver"],
)

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = ["rest_framework", "rest_framework_simplejwt"]
LOCAL_APPS = ["core", "trading", "apps.broker", "apps.deriv", "apps.market_data", "apps.indicators", "apps.analysis", "apps.execution", "apps.trading", "apps.contracts", "apps.strategies", "apps.smart_money"]
LOCAL_APPS = ["core", "trading", "apps.broker", "apps.deriv", "apps.market_data", "apps.indicators", "apps.analysis"]
LOCAL_APPS = ["core", "trading", "apps.broker", "apps.deriv", "apps.execution", "apps.trading", "apps.contracts", "apps.risk"]
LOCAL_APPS = ["core", "trading", "apps.broker", "apps.deriv", "apps.market_data", "apps.indicators", "apps.analysis", "apps.execution", "apps.trading", "apps.contracts", "apps.strategies"]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.audit_middleware.AuditMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "deriv_platform.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
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

BASE_URL = env("BASE_URL", "http://127.0.0.1:8000")
DERIV_APP_ID = env("DERIV_APP_ID", env("DERIV_OAUTH_CLIENT_ID", "33uZsD0IM0MIzc2VbaYIb"))
DERIV_API_TOKEN = env("DERIV_API_TOKEN", "")
DERIV_OAUTH_CLIENT_ID = DERIV_APP_ID
DERIV_REDIRECT_URI = env("DERIV_REDIRECT_URI", "https://giblet-squeegee-flatly.ngrok-free.dev/callback")
OPENAI_API_KEY = env("OPENAI_API_KEY", "")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=24),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
