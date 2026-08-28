import inspect
from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.brokers.adapters.base import BrokerAdapter
from apps.brokers.adapters.deriv import DerivAdapter
from apps.brokers.adapters.paper import PaperTradingAdapter
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from apps.brokers.services import BrokerRegistry, OrderManagementSystem, SmartOrderRouter


class BrokerAdapterContractTests(TestCase):
    def test_initial_adapters_implement_bal_contract(self):
        required = {name for name, value in BrokerAdapter.__dict__.items() if getattr(value, '__isabstractmethod__', False)}
        for adapter in (DerivAdapter, PaperTradingAdapter):
            missing = [name for name in required if not callable(getattr(adapter, name, None))]
            self.assertEqual(missing, [])
            self.assertFalse(inspect.isabstract(adapter))


class OrderRoutingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('phase13@example.com', 'phase13@example.com', 'pass')
        broker = Broker.objects.create(name='Paper Trading', broker_type='paper')
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=broker,
            account_id='PAPER-1',
            is_preferred=True,
            credentials={'account_type': 'demo'},
        )
        BrokerConnection.objects.create(broker=broker, broker_account=self.account, status='connected')

    def test_registry_returns_adapter_without_engine_changes(self):
        self.assertIsInstance(BrokerRegistry().adapter(self.account.broker, self.account), PaperTradingAdapter)

    def test_oms_routes_and_validates_order(self):
        order = OrderManagementSystem().create(self.user, symbol='R_100', direction='buy', stake='10', quantity='1')
        self.assertEqual(order.account, self.account)
        self.assertEqual(order.status, 'validated')

    def test_smart_router_prefers_active_account(self):
        self.assertEqual(SmartOrderRouter().route(self.user), self.account)
