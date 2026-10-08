#!/bin/sh
set -eu

export DJANGO_ENV=production

# The dedicated worker must survive transient Redis disconnects. Keep this
# worker-side retry policy independent from the HTTP publish path, which remains
# deliberately bounded and non-retrying.
export CELERY_WORKER_BROKER_RETRY=true
export CELERY_WORKER_RETRY_ON_STARTUP=true

# Schema migrations are owned by the general worker deployment. Keeping
# the dedicated market-data worker migration-free avoids concurrent migration
# connections against the shared Supabase pool during a rollout.
python manage.py check_market_data_worker

exec celery -A deriv_platform.celery worker \
  --loglevel=INFO \
  --include=apps.market_data.tasks \
  --queues=market_data \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  --max-tasks-per-child=20 \
  --hostname=market-data@%h
