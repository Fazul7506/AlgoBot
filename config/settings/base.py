"""Django base settings - shared across all environments."""
import os
from pathlib import Path
from config.settings.utils import get_bool_env, get_list_env

# Project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Core Django
SECRET_KEY = os.getenv('SECRET_KEY', os.getenv('DJANGO_SECRET_KEY', 'dev-insecure-key-change-in-production'))
DEBUG = get_bool_env('DEBUG', get_bool_env('DJANGO_DEBUG', True))
ALLOWED_HOSTS = get_list_env('ALLOWED_HOSTS', ['127.0.0.1', 'localhost', 'testserver'])
TIME_ZONE = os.getenv('TIME_ZONE', 'UTC')
LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_TZ = True

# Security
SECURE_SSL_REDIRECT = get_bool_env('SECURE_SSL_REDIRECT', False)
SESSION_COOKIE_SECURE = get_bool_env('SESSION_COOKIE_SECURE', False)
CSRF_COOKIE_SECURE = get_bool_env('CSRF_COOKIE_SECURE', False)
SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
CSRF_COOKIE_SAMESITE = os.getenv('CSRF_COOKIE_SAMESITE', 'Lax')
CSRF_TRUSTED_ORIGINS = get_list_env('CSRF_TRUSTED_ORIGINS', [])

# Installed apps
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    
    'core',
    'apps.accounts',
    'apps.admin_portal',
    'apps.ai_engine',
    'apps.alerts',
    'apps.analysis',
    'apps.analytics',
    'apps.audit',
    'apps.automation',
    'apps.backtesting',
    'apps.billing',
    'apps.broker',
    'apps.brokers',
    'apps.community',
    'apps.contracts',
    'apps.copy_trading',
    'apps.dashboard',
    'apps.deployment',
    'apps.deriv',
    'apps.developer',
    'apps.developer_api',
    'apps.enterprise',
    'apps.execution',
    'apps.feature_flags',
    'apps.feature_store',
    'apps.followers',
    'apps.health',
    'apps.indicators',
    'apps.journal',
    'apps.leaderboards',
    'apps.licensing',
    'apps.logging_system',
    'apps.market_data',
    'apps.marketplace',
    'apps.metrics',
    'apps.ml_models',
    'apps.monitoring',
    'apps.notifications',
    'apps.observability',
    'apps.optimization',
    'apps.organizations',
    'apps.paper_trading',
    'apps.portfolio',
    'apps.providers',
    'apps.rbac',
    'apps.referrals',
    'apps.reports',
    'apps.risk',
    'apps.signals',
    'apps.simulation',
    'apps.smart_money',
    'apps.strategies',
    'apps.subscriptions',
    'apps.support',
    'apps.tenants',
    'apps.trading',
    'apps.training',
    'apps.usage',
    'apps.workspace',
]

# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.audit_middleware.AuditMiddleware',
]

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    },
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
}

# JWT
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
}

# CORS
CORS_ALLOWED_ORIGINS = get_list_env('CORS_ALLOWED_ORIGINS', [
    'http://127.0.0.1:3000',
    'http://localhost:3000',
    'http://127.0.0.1:8000',
    'http://localhost:8000',
])
CORS_ALLOW_CREDENTIALS = True

# Templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Database - imported from database.py
from config.settings.database import *  # noqa: F403, F401

# Cache - imported from cache.py
from config.settings.cache import *  # noqa: F403, F401

# Email - imported from email.py
from config.settings.email import *  # noqa: F403, F401

# Broker - imported from broker.py
from config.settings.broker import *  # noqa: F403, F401

# Security - imported from security.py
from config.settings.security import *  # noqa: F403, F401

# Logging - imported from logging.py
from config.settings.logging import *  # noqa: F403, F401

# Celery - imported from celery.py
from config.settings.celery import *  # noqa: F403, F401

# Auth
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
