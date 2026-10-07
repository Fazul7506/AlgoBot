#!/bin/sh
set -eu

export DJANGO_ENV=production

python manage.py migrate --fake-initial --noinput

exec celery -A deriv_platform.celery worker \
  --loglevel=INFO \
  -Q celery \
  --concurrency=2 \
  --prefetch-multiplier=1 \
  --max-tasks-per-child=100 \
  --hostname=general@%h
