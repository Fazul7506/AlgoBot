from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.strategies.models import Strategy, StrategySignal

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
        StrategySignal.objects.create(strategy=self._strategy('Trend'), symbol="R_100", signal="BUY", confidence=90)
        StrategySignal.objects.create(strategy=self._strategy('Momentum'), symbol="R_100", signal="BUY", confidence=80)
        StrategySignal.objects.create(strategy=self._strategy('MeanRev'), symbol="R_100", signal="SELL", confidence=20)
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
        StrategySignal.objects.create(strategy=self._strategy('Trend'), symbol="R_100", signal="BUY", confidence=80)
        expired = StrategySignal.objects.create(strategy=self._strategy('MeanRev'), symbol="R_100", signal="SELL", confidence=60)
        StrategySignal.objects.filter(pk=expired.pk).update(timestamp=timezone.now() - timedelta(minutes=10))
        response = self.client.get("/api/market/signals/lifecycle/?symbol=R_100")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["signals"][0]["lifecycle"], "active")
        self.assertEqual(response.data["signals"][1]["lifecycle"], "expired")
