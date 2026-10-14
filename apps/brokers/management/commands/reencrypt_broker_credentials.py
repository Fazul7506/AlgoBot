"""Re-encrypt legacy broker token fields with the configured Fernet key.

Run once after configuring CREDENTIALS_ENCRYPTION_KEY. This command does not
print credentials and is safe to rerun; already-Fernet-encrypted fields are
left unchanged.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.brokers.models import BrokerAccount
from core.services.encryption_service import CredentialEncryptionService


class Command(BaseCommand):
    help = "Re-encrypt legacy broker access/refresh token fields at rest."

    def handle(self, *args, **options):
        encryption = CredentialEncryptionService()
        if encryption._fernet is None:
            raise CommandError("Configure a valid CREDENTIALS_ENCRYPTION_KEY before migrating broker credentials.")

        changed = 0
        with transaction.atomic():
            for account in BrokerAccount.objects.select_for_update().iterator():
                updates = []
                for field, setter in (
                    ("access_token", account.set_access_token),
                    ("refresh_token", account.set_refresh_token),
                ):
                    stored = getattr(account, field) or ""
                    if not stored or stored.startswith("gAAAA"):
                        continue
                    # decrypt() supports the old base64/plaintext fallback only
                    # for migration; the value is never printed or logged.
                    raw = encryption.decrypt(stored)
                    setter(raw)
                    updates.append(field)
                if updates:
                    account.save(update_fields=updates)
                    changed += len(updates)
        self.stdout.write(self.style.SUCCESS(
            f"Re-encrypted {changed} legacy broker token fields across existing accounts."
        ))
