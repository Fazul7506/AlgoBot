#!/usr/bin/env python3
"""Run AlgoBot's existing background processes outside Render.

This launcher starts the same canonical commands declared in render.yaml:
general Celery worker, one Celery Beat scheduler, live market stream, and
market-data worker. Secrets/configuration come only from the environment.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROCESSES = {
    "worker": [
        sys.executable, "-m", "celery", "-A", "deriv_platform.celery",
        "worker", "--loglevel=INFO", "-Q", "celery", "--concurrency=2",
        "--prefetch-multiplier=1", "--max-tasks-per-child=100",
        "--hostname=general@%h",
    ],
    "beat": [
        sys.executable, "-m", "celery", "-A", "deriv_platform.celery",
        "beat", "--loglevel=INFO", "--pidfile=/tmp/algobot-celerybeat.pid",
    ],
    "live_market_stream": [
        sys.executable, "manage.py", "run_market_stream",
    ],
    "market_data": [
        sys.executable, "-m", "celery", "-A", "deriv_platform.celery",
        "worker", "--loglevel=INFO", "--include=apps.market_data.tasks",
        "--queues=market_data", "--concurrency=1",
        "--prefetch-multiplier=1", "--max-tasks-per-child=20",
        "--hostname=market-data@%h",
    ],
}

def validate_environment() -> None:
    required = (
        "DJANGO_SETTINGS_MODULE", "DJANGO_ENV", "DATABASE_URL",
        "REDIS_URL", "SECRET_KEY", "USE_REDIS", "USE_CELERY",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(
            "Missing required worker environment variables: " + ", ".join(missing)
        )
    if os.environ.get("USE_REDIS", "").lower() != "true":
        raise SystemExit("USE_REDIS must be true for external Celery workers.")
    os.environ.setdefault("CELERY_BROKER_URL", os.environ["REDIS_URL"])
    os.environ.setdefault("CELERY_RESULT_BACKEND", os.environ["REDIS_URL"])

def main() -> int:
    validate_environment()
    children: dict[str, subprocess.Popen[str]] = {}
    stopping = False

    def stop_all(signum: int, _frame: object) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print(f"Stopping AlgoBot workers after signal {signum}...", flush=True)
        for process in children.values():
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    try:
        for name, command in PROCESSES.items():
            print(f"Starting {name}: {' '.join(command)}", flush=True)
            children[name] = subprocess.Popen(command, cwd=ROOT, env=os.environ.copy(), text=True)

        while children:
            for name, process in list(children.items()):
                code = process.poll()
                if code is None:
                    continue
                print(f"{name} exited with code {code}.", flush=True)
                if not stopping:
                    stopping = True
                    stop_all(signal.SIGTERM, None)
                children.pop(name, None)
            if children:
                signal.pause()
    finally:
        for process in children.values():
            if process.poll() is None:
                process.terminate()
        for process in children.values():
            process.wait(timeout=30)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
