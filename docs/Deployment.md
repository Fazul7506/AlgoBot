# Deployment

Production deployments should set `DJANGO_SETTINGS_MODULE=config.settings.production`, configure PostgreSQL, Redis, Celery workers, Gunicorn behind Nginx, HTTPS, `SECRET_KEY`, `ALLOWED_HOSTS`, `BASE_URL`, `DERIV_APP_ID`, and `DERIV_REDIRECT_URI`. Health endpoints are available at `/health/`, `/health/live/`, and `/health/ready/`.
