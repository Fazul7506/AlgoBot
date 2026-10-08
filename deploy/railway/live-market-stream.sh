#!/bin/sh
set -eu

export DJANGO_ENV=production

# Schema migrations are owned by the general worker deployment. Keeping
# the live stream process migration-free avoids concurrent migration
# connections against the shared Supabase pool during a rollout.
exec python manage.py run_market_stream
