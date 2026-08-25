# WhiteNoise can only serve files that have been collected into STATIC_ROOT when
# DEBUG is false.  Collect them in the release process so a fresh Render
# instance never returns empty successful responses for the application shell.
web: DJANGO_ENV=production python manage.py collectstatic --noinput && exec daphne --bind 0.0.0.0 --port $PORT deriv_platform.asgi:application
