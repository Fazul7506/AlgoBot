from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import PasswordResetToken, UserProfile
from core.services.encryption_service import CredentialEncryptionService


User = get_user_model()


class AuthenticationTokenCleanupTests(TestCase):
    def test_cleanup_removes_only_expired_auth_tokens_and_preserves_accounts(self):
        user = User.objects.create_user(
            username="cleanup-user",
            email="cleanup@example.test",
            password="Secure-cleanup-123!",
        )
        profile, _ = UserProfile.objects.update_or_create(
            user=user,
            defaults={
                "email_verified": False,
                "email_verification_token": "hashed-expired-token",
                "email_verification_token_created_at": timezone.now() - timedelta(hours=25),
            },
        )
        PasswordResetToken.objects.create(
            user=user,
            token="expired-reset-token-hash",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        output = StringIO()

        call_command("cleanup_auth_tokens", stdout=output)

        profile.refresh_from_db()
        self.assertEqual(profile.email_verification_token, "")
        self.assertIsNone(profile.email_verification_token_created_at)
        self.assertFalse(PasswordResetToken.objects.filter(user=user).exists())
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    @override_settings(CREDENTIALS_ENCRYPTION_KEY="")
    def test_credential_encryption_fails_closed_without_key(self):
        encryption = CredentialEncryptionService()
        self.assertIsNone(encryption._fernet)
        with self.assertRaises(RuntimeError):
            encryption.encrypt("provider-access-token")
