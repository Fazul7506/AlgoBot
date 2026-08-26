from django.core.management.base import BaseCommand, CommandError

from apps.market_data.historical import fetch_and_store
from apps.market_data.models import MarketSymbol


class Command(BaseCommand):
    help = "Fetch and persist historical Deriv OHLC candles for AI training."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", help="Fetch one symbol")
        parser.add_argument("--timeframe", default="M1")
        parser.add_argument("--count", type=int, default=5000)

    def handle(self, *args, **options):
        symbols = [options["symbol"]] if options["symbol"] else list(
            MarketSymbol.objects.filter(is_active=True, is_tradable=True).values_list("symbol", flat=True)
        )
        if options["count"] < 250:
            raise CommandError("--count must be at least 250 for the AI feature pipeline")

        results = {}
        for symbol in symbols:
            try:
                results[symbol] = fetch_and_store(symbol, options["timeframe"], options["count"])
                self.stdout.write(self.style.SUCCESS(f"{symbol}: {results[symbol]}"))
            except Exception as exc:
                results[symbol] = {"status": "failed", "error": str(exc)}
                self.stderr.write(self.style.ERROR(f"{symbol}: {exc}"))

        successful = sum(1 for value in results.values() if value.get("stored_total", 0) >= 250)
        failed = sum(1 for value in results.values() if value.get("status") == "failed")
        self.stdout.write(f"Historical data summary: symbols={len(results)} ready={successful} failed={failed}")
        if options["symbol"] and results[options["symbol"]].get("status") == "failed":
            raise CommandError(results[options["symbol"]]["error"])
