import os

from django.core.management.base import BaseCommand, CommandError


REQUIRED_TASK = "apps.market_data.tasks.run_initial_candle_backfill"
REQUIRED_ENV = (
    "DJANGO_ENV",
    "DATABASE_URL",
    "REDIS_URL",
    "SECRET_KEY",
    "USE_REDIS",
    "USE_CELERY",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise CommandError(f"Required Celery runtime variable is missing: {name}")
    return value


class Command(BaseCommand):
    help = "Fail fast unless the Celery market-data runtime is fully configured and reachable."

    def handle(self, *args, **options):
        for name in REQUIRED_ENV:
            _required_env(name)

        if os.getenv("DJANGO_ENV", "").strip().lower() != "production":
            raise CommandError("Celery production workers require DJANGO_ENV=production")

        if os.getenv("USE_REDIS", "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise CommandError("Celery workers require USE_REDIS=true")

        if os.getenv("USE_CELERY", "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise CommandError("Celery workers require USE_CELERY=true")

        redis_url = os.environ["REDIS_URL"]
        broker_url = os.environ["CELERY_BROKER_URL"]
        result_backend = os.environ["CELERY_RESULT_BACKEND"]
        if broker_url != redis_url:
            raise CommandError("CELERY_BROKER_URL must exactly match REDIS_URL on Render")
        if result_backend != redis_url:
            raise CommandError("CELERY_RESULT_BACKEND must exactly match REDIS_URL on Render")

        from deriv_platform.celery import app

        registered = set(app.tasks)
        if REQUIRED_TASK not in registered:
            raise CommandError(
                f"Required market-data Celery task is not registered: {REQUIRED_TASK}"
            )

        route = app.conf.task_routes or {}
        configured_queue = (route.get(REQUIRED_TASK) or {}).get("queue")
        if configured_queue != "market_data":
            raise CommandError(
                f"{REQUIRED_TASK} is routed to {configured_queue!r}, expected 'market_data'"
            )

        try:
            connection = app.connection_for_read()
            connection.ensure_connection(max_retries=1)
        except Exception as exc:
            raise CommandError(
                f"Celery broker is not reachable from the market-data worker: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Market-data Celery preflight OK: required environment present, "
                "Redis broker/backend aligned, task registered, queue=market_data, "
                "and broker reachable."
            )
        )
