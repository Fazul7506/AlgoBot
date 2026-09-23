from django.core.management.base import BaseCommand, CommandError

from apps.market_data.tasks import BACKFILL_REQUEST_INTERVAL_SECONDS, _active_symbols
from apps.market_data.historical import fetch_and_store_all_timeframes


class Command(BaseCommand):
    help = "Backfill and persist every canonical candle timeframe for active broker symbols."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", help="Backfill one symbol")
        parser.add_argument("--count", type=int, default=5000)

    def handle(self, *args, **options):
        count = int(options["count"])
        if count < 250 or count > 5000:
            raise CommandError("--count must be between 250 and 5000 per Deriv history request")

        requested_symbol = (options["symbol"] or "").strip()
        symbols = _active_symbols(requested_symbol or None)
        if requested_symbol and not symbols:
            raise CommandError("Selected symbol is not an active, tradable Deriv market symbol")
        if not symbols:
            raise CommandError("No active tradable market symbols are available")

        failed = 0
        for symbol in symbols:
            result = fetch_and_store_all_timeframes(
                symbol,
                count=count,
                request_interval=BACKFILL_REQUEST_INTERVAL_SECONDS,
            )
            failures = [
                name for name, value in result["timeframes"].items()
                if isinstance(value, dict) and value.get("status") == "failed"
            ]
            if failures:
                failed += 1
                self.stderr.write(self.style.ERROR(f"{symbol}: failed timeframes={','.join(failures)}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"{symbol}: all canonical timeframes persisted"))

        self.stdout.write(
            f"All-timeframe candle backfill complete: symbols={len(symbols)} failed_symbols={failed}"
        )
        if failed:
            raise CommandError(f"Historical backfill failed for {failed} symbol(s)")
