"""Prune expired authentication tokens without deleting user accounts."""


from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import PasswordResetToken, UserProfile


class Command(BaseCommand):
    help = "Remove expired/used password-reset tokens and clear expired email-verification token hashes."

    def handle(self, *args, **options):
        now = timezone.now()
        with transaction.atomic():
            reset_deleted, _ = PasswordResetToken.objects.filter(
                models_expired_or_used(now)
            ).delete()
            stale_verification = UserProfile.objects.filter(
                email_verified=False,
                email_verification_token__gt="",
                (
                    Q(email_verification_token_created_at__lte=now - timedelta(hours=24))
                    | Q(
                        email_verification_token_created_at__isnull=True,
                        updated_at__lte=now - timedelta(hours=24),
                    )
                ),
            )
            verification_cleared = stale_verification.update(
                email_verification_token="",
                email_verification_token_created_at=None,
            )
        self.stdout.write(self.style.SUCCESS(
            f"Deleted {reset_deleted} expired/used password-reset records; "
            f"cleared {verification_cleared} expired email-verification token hashes."
        ))


def models_expired_or_used(now):
    from django.db.models import Q
    return Q(expires_at__lte=now) | Q(used=True)
