#!/bin/sh
set -eu

export DJANGO_ENV=production

# Schema migrations are owned by the general worker deployment. This
# singleton execution process must not compete for Supavisor connections at startup.
exec celery -A deriv_platform.celery worker \
  --loglevel=INFO \
  --include=apps.execution.tasks \
  --queues=execution \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  --max-tasks-per-child=100 \
  --hostname=execution@%h
