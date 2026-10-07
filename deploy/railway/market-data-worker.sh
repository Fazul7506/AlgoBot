#!/bin/sh
set -eu

export DJANGO_ENV=production

python manage.py migrate --fake-initial --noinput
python manage.py check_market_data_worker

exec celery -A deriv_platform.celery worker \
  --loglevel=INFO \
  --include=apps.market_data.tasks \
  --queues=market_data \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  --max-tasks-per-child=20 \
  --hostname=market-data@%h
