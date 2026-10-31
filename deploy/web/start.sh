#!/usr/bin/env bash
# Run the complete AlgoBot runtime inside the single Render web service.
# This replaces the former external Worker, Beat and LiveMarketStream services.
set -Eeuo pipefail

export DJANGO_ENV="${DJANGO_ENV:-production}"
export DB_POOL_MIN_SIZE="${DB_POOL_MIN_SIZE:-0}"
export DB_POOL_MAX_SIZE="${DB_POOL_MAX_SIZE:-4}"
export DB_POOL_TIMEOUT="${DB_POOL_TIMEOUT:-20}"

python manage.py check

WEB_PID=""
WORKER_PID=""
BEAT_PID=""
STREAM_PID=""

stop_children() {
  local status=$?
  trap - EXIT INT TERM
  for pid in "$WEB_PID" "$WORKER_PID" "$BEAT_PID" "$STREAM_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  for pid in "$WEB_PID" "$WORKER_PID" "$BEAT_PID" "$STREAM_PID"; do
    if [[ -n "$pid" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
  exit "$status"
}
trap stop_children EXIT INT TERM

start_web() {
  daphne --bind 0.0.0.0 --port "$PORT" deriv_platform.asgi:application &
  WEB_PID=$!
}
start_worker() {
  celery -A deriv_platform.celery worker --loglevel=INFO -Q celery --concurrency=2 --prefetch-multiplier=1 --max-tasks-per-child=100 --hostname=web-runtime@%h &
  WORKER_PID=$!
}
start_beat() {
  celery -A deriv_platform.celery beat --loglevel=INFO --pidfile=/tmp/algobot-celerybeat.pid &
  BEAT_PID=$!
}
start_market_stream() {
  python manage.py run_market_stream &
  STREAM_PID=$!
}

start_web
start_worker
start_beat
start_market_stream

# Keep the web process authoritative. Restart a failed background component
# with bounded backoff; never allow a worker crash to silently disable a
# scheduled pipeline or the broker market feed.
while kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 5
  if ! kill -0 "$WORKER_PID" 2>/dev/null; then
    wait "$WORKER_PID" 2>/dev/null || true
    sleep 5
    start_worker
  fi
  if ! kill -0 "$BEAT_PID" 2>/dev/null; then
    wait "$BEAT_PID" 2>/dev/null || true
    sleep 5
    start_beat
  fi
  if ! kill -0 "$STREAM_PID" 2>/dev/null; then
    wait "$STREAM_PID" 2>/dev/null || true
    sleep 5
    start_market_stream
  fi
done

wait "$WEB_PID"
