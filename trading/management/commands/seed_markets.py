from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.market_data.constants import TIMEFRAMES
from apps.market_data.deriv_sync import sync_active_symbols
from apps.market_data.models import MarketSymbol as BrokerMarketSymbol
from trading.models.market import MarketSymbol as TradingMarketSymbol


MARKET_TYPE_MAP = {
    "Volatility Indices": "VOLATILITY", "Boom": "BOOM_CRASH", "Crash": "BOOM_CRASH", "Forex": "FOREX",
    "Crypto": "CRYPTO", "Derived Indices": "SYNTHETIC", "Jump Indices": "SYNTHETIC", "Commodities": "COMMODITY", "Stock Indices": "SYNTHETIC",
}


def broker_timeframe_key(key):
    """Normalize the broker data-service timeframe key for the trading catalog."""
    return str(key).strip().lower()


class Command(BaseCommand):
    help = "Synchronize the market catalogue from the broker and ensure the current model schema exists."

    def add_arguments(self, parser):
        parser.add_argument("--deactivate-missing", action="store_true", help="Deactivate trading-model symbols that are no longer returned by the broker.")

    def handle(self, *args, **options):
        call_command("makemigrations", interactive=False, verbosity=1)
        call_command("migrate", interactive=False, verbosity=1)
        synced = sync_active_symbols()
        broker_symbols = list(BrokerMarketSymbol.objects.filter(is_active=True))
        seen = set()
        created = updated = 0
        # Keep the timeframe catalog aligned with the broker data service rather than
        # maintaining a second hard-coded list in the UI. Tick is a streaming mode, not OHLC.
        supported_timeframes = [broker_timeframe_key(key) for key in TIMEFRAMES if broker_timeframe_key(key) != "tick"]

        for source in broker_symbols:
            market_type = MARKET_TYPE_MAP.get(source.market, "SYNTHETIC")
            obj, was_created = TradingMarketSymbol.objects.update_or_create(
                symbol=source.symbol,
                defaults={
                    "display_name": source.display_name,
                    "market_type": market_type,
                    "pip_size": float(source.tick_size or source.pip_size or 0),
                    "is_active": source.is_active,
                    "is_tradeable": source.is_tradable,
                    "supported_timeframes": supported_timeframes,
                },
            )
            seen.add(obj.pk)
            created += int(was_created)
            updated += int(not was_created)

        deactivated = 0
        if options["deactivate_missing"] and seen:
            deactivated = TradingMarketSymbol.objects.filter(is_active=True).exclude(pk__in=seen).update(is_active=False)

        self.stdout.write(self.style.SUCCESS(f"Broker market sync complete: {synced} broker symbols synchronized; {created} trading records created, {updated} updated, {deactivated} deactivated."))
