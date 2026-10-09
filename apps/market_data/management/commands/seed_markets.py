from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.market_data.deriv_sync import sync_active_symbols


class Command(BaseCommand):
    help = (
        "Synchronize the market catalogue from Deriv's live active_symbols "
        "response. No local/default symbol list is authoritative."
    )

    def handle(self, *args, **options):
        try:
            synced = sync_active_symbols()
        except Exception as exc:
            raise CommandError(
                "Deriv market catalogue sync failed; no fallback symbols were seeded. "
                f"Broker source of truth is unavailable: {exc}"
            ) from exc

        if synced < 1:
            raise CommandError(
                "Deriv returned no usable market symbols; refusing to seed local defaults."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Market catalogue synchronized from Deriv: {synced} broker symbols."
            )
        )
