# Web service: migrate and collect static assets before starting the ASGI server.
web: DJANGO_ENV=production python3 manage.py migrate --fake-initial --noinput && python3 manage.py collectstatic --noinput && exec daphne --bind 0.0.0.0 --port $PORT deriv_platform.asgi:application

# Render Background Worker service: select this process type so queued backtests
# and other asynchronous jobs are actually consumed. Keep the worker separate
# from the web process so CPU-heavy research cannot starve HTTP requests.
worker: DJANGO_ENV=production celery -A deriv_platform.celery worker --loglevel=INFO --concurrency=1 --prefetch-multiplier=1

# Optional Render Cron/Background Worker process for periodic Celery schedules.
beat: DJANGO_ENV=production celery -A deriv_platform.celery beat --loglevel=INFO
