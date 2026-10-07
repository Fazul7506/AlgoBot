#!/bin/sh
set -eu

export DJANGO_ENV=production

python manage.py migrate --fake-initial --noinput

exec celery -A deriv_platform.celery beat \
  --loglevel=INFO \
  --pidfile=/tmp/algobot-celerybeat.pid
