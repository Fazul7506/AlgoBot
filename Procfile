# Apply database migrations before serving a new release. This keeps the deployed
# schema synchronized with the code before requests reach the service.
# Collect static assets for WhiteNoise when DEBUG is false.
web: DJANGO_ENV=production python manage.py migrate --noinput && python manage.py collectstatic --noinput && exec daphne --bind 0.0.0.0 --port $PORT deriv_platform.asgi:application
