from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.brokers.models import Broker, BrokerAccount
from core.views_broker_oauth import _persist_deriv_account


class DerivOAuthAccountOwnershipTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="deriv-account-owner")
        self.other_user = User.objects.create_user(username="deriv-account-other-user")
        self.broker = Broker.objects.create(
            name="Deriv Ownership Test",
            broker_type="deriv",
            status="active",
            metadata={"auth": "oauth"},
        )
        self.account = BrokerAccount.objects.create(
            user=self.owner,
            broker=self.broker,
            account_id="CR12345",
            credentials={"account_type": "real", "marker": "owner-data"},
            status="active",
        )
        self.account.set_access_token("owner-access-token")
        self.account.set_refresh_token("owner-refresh-token")
        self.account.save(update_fields=["access_token", "refresh_token"])

    def test_oauth_persistence_never_reassigns_an_account_to_another_user(self):
        original_access_token = self.account.access_token
        original_refresh_token = self.account.refresh_token
        original_credentials = self.account.credentials.copy()

        result = _persist_deriv_account(
            user=self.other_user,
            broker=self.broker,
            record={"account_id": "CR12345", "account_type": "demo", "balance": 1},
            access_token="attacker-access-token",
            refresh_token="attacker-refresh-token",
            expires_at=None,
        )

        self.assertIsNone(result)
        self.account.refresh_from_db()
        self.assertEqual(self.account.user_id, self.owner.pk)
        self.assertEqual(self.account.access_token, original_access_token)
        self.assertEqual(self.account.refresh_token, original_refresh_token)
        self.assertEqual(self.account.credentials, original_credentials)
