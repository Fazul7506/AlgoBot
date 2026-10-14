"""Re-encrypt legacy broker token fields with the configured Fernet key.

Run once after configuring CREDENTIALS_ENCRYPTION_KEY. This command does not
print credentials and is safe to rerun; already-Fernet-encrypted fields are
left unchanged.
"""
import base64

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
                    if not stored:
                        continue
                    if stored.startswith("gAAAA"):
                        # Validate that the configured key can decrypt already
                        # encrypted values before skipping them.
                        encryption.decrypt(stored)
                        continue
                    # Decode only the legacy reversible encoding here. Normal
                    # runtime reads refuse these values until re-encryption.
                    raw = stored
                    try:
                        decoded_bytes = base64.b64decode(
                            stored.encode("utf-8"), altchars=b"-_", validate=True
                        )
                        decoded = decoded_bytes.decode("utf-8")
                        # Decode only values that exactly round-trip through the
                        # legacy URL-safe Base64 encoder; otherwise treat the
                        # field as a legacy plaintext token and encrypt it.
                        if base64.urlsafe_b64encode(decoded.encode("utf-8")).decode("ascii") == stored:
                            raw = decoded
                    except (ValueError, UnicodeDecodeError):
                        raw = stored
                    if not raw:
                        continue
                    setter(raw)
                    updates.append(field)
                if updates:
                    account.save(update_fields=updates)
                    changed += len(updates)
        self.stdout.write(self.style.SUCCESS(
            f"Re-encrypted {changed} legacy broker token fields across existing accounts."
        ))
