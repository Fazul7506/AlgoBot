from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.brokers.models import Broker, BrokerAccount
from core.views_oauth import _persist_refreshed_credentials


class DerivTokenRefreshTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="deriv-refresh-user")
        broker = Broker.objects.create(
            name="Deriv Refresh Test",
            broker_type="deriv",
            status="active",
            metadata={"auth": "oauth"},
        )
        self.active_one = BrokerAccount.objects.create(
            user=user, broker=broker, account_id="CR-ACTIVE-1", status="active",
            token_status="expired", credentials={"account_type": "demo"},
        )
        self.active_two = BrokerAccount.objects.create(
            user=user, broker=broker, account_id="CR-ACTIVE-2", status="active",
            token_status="expired", credentials={"account_type": "real"},
        )
        self.disabled = BrokerAccount.objects.create(
            user=user, broker=broker, account_id="CR-DISABLED", status="disabled",
            token_status="revoked", credentials={"account_type": "real"},
        )
        for account in (self.active_one, self.active_two, self.disabled):
            account.set_access_token(f"old-access-{account.account_id}")
            account.set_refresh_token(f"old-refresh-{account.account_id}")
            account.save(update_fields=["access_token", "refresh_token"])

    def test_rotated_tokens_update_active_accounts_without_reactivating_disabled_accounts(self):
        _persist_refreshed_credentials(
            self.active_one,
            {"access_token": "rotated-access", "refresh_token": "rotated-refresh", "expires_in": 3600},
        )

        for account in (self.active_one, self.active_two):
            account.refresh_from_db()
            self.assertEqual(account.get_access_token(), "rotated-access")
            self.assertEqual(account.get_refresh_token(), "rotated-refresh")
            self.assertEqual(account.token_status, "active")
            self.assertIsNotNone(account.expires_at)

        self.disabled.refresh_from_db()
        self.assertEqual(self.disabled.status, "disabled")
        self.assertEqual(self.disabled.token_status, "revoked")
        self.assertEqual(self.disabled.get_access_token(), "old-access-CR-DISABLED")
        self.assertEqual(self.disabled.get_refresh_token(), "old-refresh-CR-DISABLED")

    def test_missing_refreshed_access_token_is_rejected(self):
        with self.assertRaises(ValueError):
            _persist_refreshed_credentials(self.active_one, {"expires_in": 3600})
