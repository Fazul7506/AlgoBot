"""Report safe connectivity status for configured AI providers."""
from django.core.management.base import BaseCommand

from apps.brokers.ai_provider_utils import provider_health_report


class Command(BaseCommand):
    help = "Check configured AI provider endpoints and credentials without printing secrets."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=10, help="Per-provider request timeout in seconds.")

    def handle(self, *args, **options):
        reports = provider_health_report(timeout=max(1, min(options["timeout"], 30)))
        if not reports:
            self.stdout.write(self.style.WARNING(
                "No AI providers configured. Set one or more provider API keys in deployment environment secrets."
            ))
            return
        failed = False
        for item in reports:
            if item["status"] == "reachable":
                self.stdout.write(self.style.SUCCESS(f'{item["provider"]}: reachable — {item["detail"]}'))
            else:
                failed = True
                self.stdout.write(self.style.WARNING(f'{item["provider"]}: unavailable — {item["detail"]}'))
        if failed:
            self.stdout.write(self.style.WARNING(
                "At least one provider is unavailable. Health checks verify endpoint/key access, not quota for every model or successful generation."
            ))
