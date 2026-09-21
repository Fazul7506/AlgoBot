from django.core.management.base import BaseCommand, CommandError


REQUIRED_TASK = "apps.market_data.tasks.run_initial_candle_backfill"


class Command(BaseCommand):
    help = "Validate that the market-data Celery worker can register its required task."

    def handle(self, *args, **options):
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
                "Market-data worker preflight OK: task registered, "
                "queue=market_data, broker reachable."
            )
        )
