from django.core.management.base import BaseCommand
from apps.brokers.models import BrokerIntegrationRun
from apps.brokers.github_sync import sync_integration_run, GitHubSyncError

class Command(BaseCommand):
    help = "Refresh broker integration PR and CI state from GitHub."
    def handle(self, *args, **options):
        runs = BrokerIntegrationRun.objects.exclude(pull_request_number__isnull=True).exclude(status="merged")
        ok = failed = 0
        for run in runs.iterator():
            try:
                data = sync_integration_run(run)
                ok += 1
                self.stdout.write(f"PR #{run.pull_request_number}: checks_passed={data['checks_passed']} merge_ready={data['merge_ready']}")
            except GitHubSyncError as exc:
                failed += 1
                self.stderr.write(f"PR #{run.pull_request_number}: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Synchronized {ok} run(s); {failed} failed."))
