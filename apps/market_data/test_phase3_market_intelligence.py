from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.strategies.models import Strategy, StrategyConfiguration, StrategySignal
from apps.brokers.models import Broker, BrokerAccount, BrokerConnection

from .models import MarketSnapshot, MarketSymbol


class Phase3MarketIntelligenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="phase3", password="test-password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.market = MarketSymbol.objects.create(
            symbol="R_100",
            display_name="Volatility 100 Index",
            market="synthetic_index",
            is_active=True,
            is_tradable=True,
        )
        self.broker = Broker.objects.create(name="Deriv Phase3", broker_type="deriv")
        self.account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id="phase3-account",
            credentials={"account_type": "demo"}, token_status="active",
        )
        BrokerConnection.objects.create(broker=self.broker, broker_account=self.account, status="connected")

    def _strategy(self, name):
        return Strategy.objects.create(name=name, slug=name.lower().replace(' ', '-'), category='Momentum')

    def test_intelligence_requires_authentication(self):
        response = APIClient().get("/api/market/intelligence/")
        self.assertIn(response.status_code, {401, 403})

    def test_intelligence_marks_stale_snapshot_without_fabricating_freshness(self):
        MarketSnapshot.objects.create(
            symbol=self.market,
            last_price="100.0",
            change_percent="1.0",
            timestamp=timezone.now() - timedelta(seconds=90),
        )
        response = self.client.get("/api/market/intelligence/?symbol=R_100")
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertEqual(row["status"], "stale")
        self.assertFalse(row["fresh"])
        self.assertGreaterEqual(row["freshness_seconds"], 90)

    def test_fresh_only_excludes_stale_market(self):
        MarketSnapshot.objects.create(
            symbol=self.market,
            last_price="100.0",
            timestamp=timezone.now() - timedelta(seconds=90),
        )
        response = self.client.get("/api/market/intelligence/?symbol=R_100&fresh_only=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_signal_confluence_reports_direction_confidence_and_timeframes(self):
        MarketSnapshot.objects.create(
            symbol=self.market,
            last_price="100.0",
            change_percent="1.0",
            timestamp=timezone.now(),
        )
        for strategy, signal, confidence in [
            (self._strategy('Trend'), "BUY", 90),
            (self._strategy('Momentum'), "BUY", 80),
            (self._strategy('MeanRev'), "SELL", 20),
        ]:
            config = StrategyConfiguration.objects.create(
                strategy=strategy, user=self.user, broker_account=self.account,
                symbol="R_100", timeframe="M1",
            )
            StrategySignal.objects.create(
                strategy=strategy, configuration=config, symbol="R_100",
                signal=signal, confidence=confidence,
            )
        response = self.client.get("/api/market/intelligence/?symbol=R_100")
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertEqual(row["dominant_direction"], "BUY")
        self.assertEqual(row["buy_signals"], 2)
        self.assertEqual(row["sell_signals"], 1)
        self.assertEqual(row["timeframes"], [])
        self.assertGreater(row["signal_strength"], 0)
        self.assertIn("signal_confluence_buy", row["evidence"])

    def test_signal_lifecycle_exposes_active_and_expired_states(self):
        trend = self._strategy('Trend')
        mean_rev = self._strategy('MeanRev')
        trend_config = StrategyConfiguration.objects.create(
            strategy=trend, user=self.user, broker_account=self.account,
            symbol="R_100", timeframe="M1",
        )
        mean_config = StrategyConfiguration.objects.create(
            strategy=mean_rev, user=self.user, broker_account=self.account,
            symbol="R_100", timeframe="M1",
        )
        StrategySignal.objects.create(strategy=trend, configuration=trend_config, symbol="R_100", signal="BUY", confidence=80)
        expired = StrategySignal.objects.create(strategy=mean_rev, configuration=mean_config, symbol="R_100", signal="SELL", confidence=60)
        StrategySignal.objects.filter(pk=expired.pk).update(timestamp=timezone.now() - timedelta(minutes=10))
        response = self.client.get("/api/market/signals/lifecycle/?symbol=R_100")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["signals"][0]["lifecycle"], "active")
        self.assertEqual(response.data["signals"][1]["lifecycle"], "expired")
