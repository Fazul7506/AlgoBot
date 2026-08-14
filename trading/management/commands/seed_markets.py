from django.core.management.base import BaseCommand
from trading.models.market import MarketSymbol

MARKETS = [
    {"symbol": "R_10", "display_name": "Volatility 10 Index", "market_type": "VOLATILITY", "pip_size": 0.01},
    {"symbol": "R_25", "display_name": "Volatility 25 Index", "market_type": "VOLATILITY", "pip_size": 0.01},
    {"symbol": "R_50", "display_name": "Volatility 50 Index", "market_type": "VOLATILITY", "pip_size": 0.01},
    {"symbol": "R_75", "display_name": "Volatility 75 Index", "market_type": "VOLATILITY", "pip_size": 0.01},
    {"symbol": "R_100", "display_name": "Volatility 100 Index", "market_type": "VOLATILITY", "pip_size": 0.01},
    {"symbol": "BOOM", "display_name": "Boom Index", "market_type": "BOOM_CRASH", "pip_size": 0.01},
    {"symbol": "CRASH", "display_name": "Crash Index", "market_type": "BOOM_CRASH", "pip_size": 0.01},
    {"symbol": "EURUSD", "display_name": "Euro / US Dollar", "market_type": "FOREX", "pip_size": 0.0001},
]

DEFAULTS = {
    "description": "AlgoBot supported market symbol",
    "min_stake": 0.35,
    "max_stake": 50000.0,
    "is_active": True,
    "is_tradeable": True,
    "supported_timeframes": ["M1", "M5", "M15", "M30", "H1", "H4", "D1"],
    "timezone": "UTC",
}


class Command(BaseCommand):
    help = "Create/update the canonical AlgoBot market symbol catalogue. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Deactivate active symbols not present in the canonical seed catalogue.",
        )

    def handle(self, *args, **options):
        seeded = set()
        created = updated = 0

        for market in MARKETS:
            defaults = {**DEFAULTS, **market}
            symbol = market["symbol"]
            obj, was_created = MarketSymbol.objects.update_or_create(
                symbol=symbol,
                defaults=defaults,
            )
            seeded.add(obj.pk)
            created += int(was_created)
            updated += int(not was_created)

        deactivated = 0
        if options["deactivate_missing"]:
            deactivated = MarketSymbol.objects.filter(is_active=True).exclude(pk__in=seeded).update(is_active=False)

        self.stdout.write(self.style.SUCCESS(
            f"Market seed complete: {created} created, {updated} updated, {deactivated} deactivated. "
            f"Total active symbols: {MarketSymbol.objects.filter(is_active=True).count()}"
        ))
