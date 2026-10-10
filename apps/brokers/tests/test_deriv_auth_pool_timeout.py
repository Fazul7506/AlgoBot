from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.brokers.adapters.deriv import DerivAdapter
from apps.brokers.exceptions import BrokerAuthenticationError


class AccountWithoutBrokerRelation:
    """Represent an account loaded without select_related('broker')."""

    broker_id = 7
    token_status = "active"
    is_token_expired = False

    @property
    def broker(self):
        raise AssertionError("Deriv token validation must not lazy-load account.broker")

    def get_access_token(self):
        return "test-access-token"


class DerivAuthPoolTimeoutRegressionTests(SimpleTestCase):
    def test_token_validation_uses_loaded_foreign_key_id_without_relation_query(self):
        adapter = DerivAdapter(
            broker=SimpleNamespace(pk=7, broker_type="deriv"),
            account=AccountWithoutBrokerRelation(),
        )

        self.assertEqual(adapter._token(), "test-access-token")

    def test_token_validation_rejects_account_from_different_broker(self):
        adapter = DerivAdapter(
            broker=SimpleNamespace(pk=8, broker_type="deriv"),
            account=AccountWithoutBrokerRelation(),
        )

        with self.assertRaisesMessage(
            BrokerAuthenticationError, "A connected Deriv account is required"
        ):
            adapter._token()
