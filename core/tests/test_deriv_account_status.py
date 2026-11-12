from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.brokers.models import Broker, BrokerAccount
from core.views_oauth import _serialize
from core.views_broker_oauth import _account_type


class DerivAccountStatusTests(TestCase):
    def test_missing_provider_account_type_is_not_inferred_as_real(self):
        self.assertEqual(_account_type({}), "unknown")
        self.assertEqual(_account_type({"is_virtual": True}), "demo")
        self.assertEqual(_account_type({"account_type": "real"}), "real")

    def test_numeric_and_string_is_virtual_flags_are_normalized(self):
        self.assertEqual(_account_type({"is_virtual": 1}), "demo")
        self.assertEqual(_account_type({"is_virtual": 0}), "real")
        self.assertEqual(_account_type({"is_virtual": "1"}), "demo")
        self.assertEqual(_account_type({"is_virtual": "0"}), "real")
        self.assertEqual(_account_type({"is_virtual": "unknown"}), "unknown")

    def test_conflicting_provider_environment_metadata_fails_closed(self):
        self.assertEqual(
            _account_type({"account_type": "demo", "is_virtual": 0}),
            "unknown",
        )

    def test_missing_account_type_is_not_misreported_as_demo(self):
        user = get_user_model().objects.create_user(username="unknown-deriv-type")
        broker = Broker.objects.create(
            name="Deriv Unknown Type Test",
            broker_type="deriv",
            status="active",
            metadata={"auth": "oauth"},
        )
        account = BrokerAccount.objects.create(
            user=user,
            broker=broker,
            account_id="UNKNOWN-TYPE",
            credentials={},
        )

        self.assertEqual(_serialize(account)["account_type"], "unknown")
