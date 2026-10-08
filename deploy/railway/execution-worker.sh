#!/bin/sh
set -eu

export DJANGO_ENV=production

python manage.py migrate --fake-initial --noinput

exec celery -A deriv_platform.celery worker \
  --loglevel=INFO \
  --include=apps.execution.tasks \
  --queues=execution \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  --max-tasks-per-child=100 \
  --hostname=execution@%h
