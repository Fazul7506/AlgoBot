from django.test import TestCase
from apps.brokers.exceptions import BrokerRoutingError
from apps.brokers.models import Broker
from apps.brokers.services import BrokerManager, BrokerRegistry

class PersistentBrokerRegistrationTests(TestCase):
    def test_registration_persists_without_enabling_live_trading(self):
        broker = BrokerManager().register_broker('binance', 'apps.brokers.adapters.binance.BinanceAdapter', name='Test Binance')
        broker.refresh_from_db()
        self.assertEqual(broker.metadata['adapter_path'], 'apps.brokers.adapters.binance.BinanceAdapter')
        self.assertEqual(broker.status, 'coming_soon')
        self.assertFalse(broker.supports_live)
        self.assertTrue(issubclass(BrokerRegistry().get('binance'), object))
    def test_unknown_type_and_invalid_adapter_are_rejected(self):
        with self.assertRaises(BrokerRoutingError): BrokerManager().register_broker('made_up', 'apps.brokers.adapters.binance.BinanceAdapter')
        with self.assertRaises(BrokerRoutingError): BrokerManager().register_broker('binance', 'os.path.join')
        with self.assertRaises(BrokerRoutingError): BrokerManager().register_broker('binance', 'apps.brokers.adapters.binance.DoesNotExist')
    def test_existing_disabled_broker_stays_disabled(self):
        broker = Broker.objects.create(name='Existing Binance', broker_type='binance', status='disabled', supports_live=False)
        result = BrokerManager().register_broker('binance', 'apps.brokers.adapters.binance.BinanceAdapter')
        broker.refresh_from_db()
        self.assertEqual(result.pk, broker.pk)
        self.assertEqual(broker.status, 'disabled')
        self.assertFalse(broker.supports_live)
