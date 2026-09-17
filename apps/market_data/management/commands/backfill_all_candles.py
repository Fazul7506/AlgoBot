from django.core.management.base import BaseCommand, CommandError

from apps.market_data.historical import fetch_and_store_all_timeframes
from apps.market_data.models import MarketSymbol


class Command(BaseCommand):
    help = "Backfill and persist every canonical candle timeframe for active broker symbols."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", help="Backfill one symbol")
        parser.add_argument("--count", type=int, default=5000)

    def handle(self, *args, **options):
        count = int(options["count"])
        if count < 250:
            raise CommandError("--count must be at least 250 for research and AI warm-up history")

        symbols = [options["symbol"]] if options["symbol"] else list(
            MarketSymbol.objects.filter(is_active=True, is_tradable=True)
            .order_by("symbol")
            .values_list("symbol", flat=True)
        )
        if not symbols:
            raise CommandError("No active tradable market symbols are available")

        failed = 0
        for symbol in symbols:
            result = fetch_and_store_all_timeframes(symbol, count=count)
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
        if options["symbol"] and failed:
            raise CommandError(f"Historical backfill failed for {options['symbol']}")
