from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand

from apps.brokers.models import BrokerAccount
from apps.execution.recovery import ExecutionRecoveryService


class Command(BaseCommand):
    help = "Recover ambiguous Deriv executions from broker-authoritative state"

    def add_arguments(self, parser):
        parser.add_argument("--account", type=int, default=None)

    def handle(self, *args, **options):
        queryset = BrokerAccount.objects.select_related("broker").filter(
            broker__broker_type="deriv",
            status="active",
            broker__status="active",
        )
        if options["account"]:
            queryset = queryset.filter(pk=options["account"])
        accounts = list(queryset)
        if not accounts:
            self.stdout.write(self.style.SUCCESS("No active Deriv accounts require execution recovery"))
            return
        service = ExecutionRecoveryService()
        for account in accounts:
            result = async_to_sync(service.recover_account)(account)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{account.account_id}: {result['recovered']} recovered, {result['unresolved']} unresolved"
                )
            )
