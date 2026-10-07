#!/usr/bin/env bash
set -euo pipefail

python manage.py check
python manage.py check_market_data_worker

celery -A deriv_platform.celery beat --loglevel=INFO --pidfile=/tmp/algobot-celerybeat.pid &
BEAT_PID=$!

celery -A deriv_platform.celery worker --loglevel=INFO -Q celery --concurrency=2 --prefetch-multiplier=1 --max-tasks-per-child=100 --hostname=general@%h &
WORKER_PID=$!

celery -A deriv_platform.celery worker --loglevel=INFO --include=apps.market_data.tasks --queues=market_data --concurrency=1 --prefetch-multiplier=1 --max-tasks-per-child=20 --hostname=market-data@%h &
MARKET_PID=$!

python manage.py run_market_stream &
STREAM_PID=$!

cleanup() {
  status=$?
  kill "$BEAT_PID" "$WORKER_PID" "$MARKET_PID" "$STREAM_PID" 2>/dev/null || true
  wait "$BEAT_PID" "$WORKER_PID" "$MARKET_PID" "$STREAM_PID" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT INT TERM

while true; do
  for pid in "$BEAT_PID" "$WORKER_PID" "$MARKET_PID" "$STREAM_PID"; do
    kill -0 "$pid" 2>/dev/null || exit 1
  done
  sleep 20
done
