"""Run the canonical broker -> AlgoBot realtime synchronization worker."""

import asyncio

from django.core.management.base import BaseCommand

from apps.brokers.realtime_sync import sync_active_deriv_accounts


class Command(BaseCommand):
    help = "Maintain authoritative Deriv WebSocket streams and synchronize them into AlgoBot."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting AlgoBot broker realtime synchronization worker"))
        try:
            asyncio.run(sync_active_deriv_accounts())
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Broker realtime synchronization worker stopped"))
