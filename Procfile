# Apply database migrations before serving a release. --fake-initial lets an existing
# production database adopt the stable initial migration state without replaying
# CREATE TABLE/index operations that already exist. New databases still run normally.
# Collect static assets for WhiteNoise when DEBUG is false.
web: DJANGO_ENV=production python manage.py migrate --fake-initial --noinput && python manage.py collectstatic --noinput && exec daphne --bind 0.0.0.0 --port $PORT deriv_platform.asgi:application
