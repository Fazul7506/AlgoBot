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

# Reap the exact child that exits. kill -0 alone is insufficient because
# an exited child can remain a zombie until wait() reaps it.
while true; do
  exited_pid=""
  if wait -n -p exited_pid "$WEB_PID" "$WORKER_PID" "$BEAT_PID" "$STREAM_PID"; then
    exit_status=0
  else
    exit_status=$?
  fi

  case "$exited_pid" in
    "$WEB_PID")
      echo "AlgoBot web server exited (status=$exit_status)" >&2
      exit "$exit_status"
      ;;
    "$WORKER_PID")
      echo "Celery worker exited (status=$exit_status); restarting" >&2
      sleep 5
      start_worker
      ;;
    "$BEAT_PID")
      echo "Celery Beat exited (status=$exit_status); restarting" >&2
      sleep 5
      start_beat
      ;;
    "$STREAM_PID")
      echo "Deriv market stream exited (status=$exit_status); restarting" >&2
      sleep 5
      start_market_stream
      ;;
    *)
      echo "Runtime supervisor could not identify an exited child" >&2
      exit 1
      ;;
  esac
done
