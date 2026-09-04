from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.market_data.models import MarketSymbol


# Stable fallback symbols used when the broker metadata endpoint is unavailable.
# The command is intentionally idempotent so it is safe to run on every deploy.
DEFAULT_SYMBOLS = (
    ("R_10", "Volatility 10 Index", "Volatility Indices", "Standard"),
    ("R_25", "Volatility 25 Index", "Volatility Indices", "Standard"),
    ("R_50", "Volatility 50 Index", "Volatility Indices", "Standard"),
    ("R_75", "Volatility 75 Index", "Volatility Indices", "Standard"),
    ("R_100", "Volatility 100 Index", "Volatility Indices", "Standard"),
    ("R_150", "Volatility 150 Index", "Volatility Indices", "Standard"),
    ("R_200", "Volatility 200 Index", "Volatility Indices", "Standard"),
    ("1HZ10V", "Volatility 10 (1s) Index", "Volatility Indices", "1 Second"),
    ("1HZ25V", "Volatility 25 (1s) Index", "Volatility Indices", "1 Second"),
    ("1HZ50V", "Volatility 50 (1s) Index", "Volatility Indices", "1 Second"),
    ("1HZ75V", "Volatility 75 (1s) Index", "Volatility Indices", "1 Second"),
    ("1HZ100V", "Volatility 100 (1s) Index", "Volatility Indices", "1 Second"),
    ("BOOM1000", "Boom 1000 Index", "Boom", "Standard"),
    ("BOOM500", "Boom 500 Index", "Boom", "Standard"),
    ("CRASH1000", "Crash 1000 Index", "Crash", "Standard"),
    ("CRASH500", "Crash 500 Index", "Crash", "Standard"),
)


class Command(BaseCommand):
    help = "Seed the canonical market symbol catalogue (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-inactive",
            action="store_true",
            help="Mark seeded symbols active/tradable; never deletes market data.",
        )

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for symbol, display_name, market, sub_market in DEFAULT_SYMBOLS:
            defaults = {
                "broker": "deriv",
                "display_name": display_name,
                "market": market,
                "sub_market": sub_market,
                "is_active": True,
                "is_tradable": True,
            }
            obj, was_created = MarketSymbol.objects.update_or_create(
                symbol=symbol,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        if options["reset_inactive"]:
            MarketSymbol.objects.filter(symbol__in=[row[0] for row in DEFAULT_SYMBOLS]).update(
                is_active=True,
                is_tradable=True,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Market catalogue ready: {created} created, {updated} updated, "
                f"{len(DEFAULT_SYMBOLS)} canonical symbols checked."
            )
        )
