#!/bin/sh
set -eu

export DJANGO_ENV=production

# Schema migrations are owned by the general worker deployment. Keeping
# singleton runtime workers migration-free avoids concurrent migration/check
# connections against the shared Supabase pool during a rollout.
exec celery -A deriv_platform.celery beat \
  --loglevel=INFO \
  --pidfile=/tmp/algobot-celerybeat.pid
