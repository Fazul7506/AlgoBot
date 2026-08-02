from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.broker.models import Broker, BrokerAccount, BrokerToken
from apps.broker.managers import BrokerManager
from apps.deriv.adapter import DerivAdapter

class BrokerLayerTests(TestCase):
    def test_deriv_adapter_is_resolved_by_broker_manager(self):
        user = get_user_model().objects.create_user(username="u", password="p")
        broker = Broker.objects.create(name="Deriv", slug="deriv")
        account = BrokerAccount.objects.create(user=user, broker=broker, broker_account_id="CR1")
        self.assertIsInstance(BrokerManager().get_adapter(account), DerivAdapter)
    def test_tokens_are_stored_encrypted(self):
        user = get_user_model().objects.create_user(username="u2", password="p")
        broker = Broker.objects.create(name="Deriv2", slug="deriv2")
        account = BrokerAccount.objects.create(user=user, broker=broker, broker_account_id="CR2")
        token = BrokerToken(broker_account=account); token.set_access_token("secret"); token.save()
        self.assertNotEqual(token.access_token, "secret"); self.assertEqual(token.get_access_token(), "secret")
