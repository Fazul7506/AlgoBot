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
# Render and Railway deploy independently. Wait briefly for the general worker's migrations, but fail closed after a bounded timeout.
python manage.py wait_for_market_data_worker_schema --timeout "${MARKET_DATA_SCHEMA_WAIT_SECONDS:-300}" --interval "${MARKET_DATA_SCHEMA_WAIT_INTERVAL:-5}"

exec celery -A deriv_platform.celery worker \
  --loglevel=INFO \
  --include=apps.market_data.tasks \
  --queues=market_data \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  --max-tasks-per-child=20 \
  --hostname=market-data@%h
