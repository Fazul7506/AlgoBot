#!/bin/sh
set -eu

export DJANGO_ENV=production

python manage.py migrate --fake-initial --noinput

exec python manage.py run_market_stream
