from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.market_data.models import MarketSnapshot, MarketSymbol

from .models import Broker, BrokerAccount, BrokerConnection
from .services import BrokerRoutingError, MarketDataFreshnessService, OrderManagementSystem, SmartOrderRouter


User = get_user_model()


class TradingFoundationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='phase1-user', password='test-password')
        self.paper = Broker.objects.create(
            name='Paper Trading',
            broker_type='paper',
            status='active',
            supports_demo=True,
            supports_live=False,
            metadata={'auth': 'none'},
        )

    def make_account(self, account_id, preferred=False, account_type='demo', broker=None):
        broker = broker or self.paper
        account = BrokerAccount.objects.create(
            user=self.user,
            broker=broker,
            account_id=account_id,
            is_preferred=preferred,
            credentials={'account_type': account_type},
        )
        BrokerConnection.objects.create(
            broker=broker,
            broker_account=account,
            status='connected',
            last_ping=timezone.now(),
            connected_at=timezone.now(),
        )
        return account

    def test_global_selector_uses_preferred_connected_account(self):
        first = self.make_account('PREF-1', preferred=True)
        self.make_account('OTHER-1', preferred=False)

        selected = SmartOrderRouter().route(self.user)

        self.assertEqual(selected.pk, first.pk)

    def test_environment_mismatch_is_rejected_before_order_creation(self):
        account = self.make_account('DEMO-1', preferred=True, account_type='demo')

        with self.assertRaisesMessage(BrokerRoutingError, 'Execution environment mismatch'):
            OrderManagementSystem().create(
                self.user,
                account=account,
                symbol='R_100',
                direction='rise',
                order_type='market',
                stake=1,
                routing_context={'account_type': 'real'},
            )

    def test_real_account_is_blocked_when_live_trading_is_disabled(self):
        live_broker = Broker.objects.create(
            name='Deriv',
            broker_type='deriv',
            status='active',
            supports_demo=True,
            supports_live=True,
            metadata={'auth': 'oauth'},
        )
        account = self.make_account('REAL-1', preferred=True, account_type='real', broker=live_broker)

        with override_settings(ALLOW_LIVE_TRADING=False):
            with self.assertRaisesMessage(BrokerRoutingError, 'Live-money trading is disabled'):
                OrderManagementSystem().create(
                    self.user,
                    account=account,
                    symbol='R_100',
                    direction='rise',
                    order_type='market',
                    stake=1,
                    routing_context={'account_type': 'real'},
                )

    def test_freshness_gate_accepts_recent_snapshot(self):
        symbol = MarketSymbol.objects.create(symbol='R_100', display_name='Volatility 100', market='Volatility Indices')
        snapshot = MarketSnapshot.objects.create(
            symbol=symbol,
            last_price='100.0',
            timestamp=timezone.now(),
        )

        self.assertEqual(MarketDataFreshnessService(max_age_seconds=30).latest('R_100').pk, snapshot.pk)

    def test_freshness_gate_rejects_stale_snapshot(self):
        symbol = MarketSymbol.objects.create(symbol='R_101', display_name='Volatility 101', market='Volatility Indices')
        MarketSnapshot.objects.create(
            symbol=symbol,
            last_price='101.0',
            timestamp=timezone.now() - timedelta(seconds=31),
        )

        with self.assertRaisesMessage(BrokerRoutingError, 'Market data for R_101 is stale'):
            MarketDataFreshnessService(max_age_seconds=30).latest('R_101')
