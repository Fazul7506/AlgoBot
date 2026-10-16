"""Wait for the general worker's schema migration before starting MarketData."""
from io import StringIO
from time import monotonic, sleep

from django.core.management import BaseCommand, CommandError, call_command


_RETRYABLE_PREFIXES = (
    "Required database table ",
    "The configured application database is not reachable from the market-data worker:",
)


class Command(BaseCommand):
    help = (
        "Wait a bounded period for the application schema to be ready, then "
        "run the full market-data worker preflight."
    )

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=300)
        parser.add_argument("--interval", type=int, default=5)

    def handle(self, *args, **options):
        timeout = max(0, options["timeout"])
        interval = max(1, options["interval"])
        deadline = monotonic() + timeout

        while True:
            try:
                # Keep transient preflight failures out of the deploy log; the
                # final timeout message is actionable without leaking DB URLs.
                call_command(
                    "check_market_data_worker",
                    stdout=StringIO(),
                    stderr=StringIO(),
                )
            except CommandError as exc:
                message = str(exc)
                if not message.startswith(_RETRYABLE_PREFIXES):
                    raise
                if monotonic() >= deadline:
                    raise CommandError(
                        "Timed out waiting for the application database schema "
                        "to finish migrating. Check the general-worker migration "
                        "logs and confirm both workers use the intended DATABASE_URL."
                    ) from None
                sleep(min(interval, max(0, deadline - monotonic())))
                continue

            self.stdout.write(
                self.style.SUCCESS(
                    "Market-data worker preflight passed after schema readiness check."
                )
            )
            return
