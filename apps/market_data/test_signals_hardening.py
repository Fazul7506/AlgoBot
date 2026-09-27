from types import SimpleNamespace
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from django.utils import timezone

from apps.market_data.signal_views import _analysis_baselines, _revise_signal
from apps.strategies.models import Strategy, StrategyConfiguration, StrategySignal
from apps.strategies.views import StrategyViewSet


class SignalRevisionIntegrityTests(SimpleTestCase):
    def _signal(self, **overrides):
        strategy = SimpleNamespace(name="Test Strategy", version="1.0", category="Test")
        values = {
            "id": 7,
            "signal": "BUY",
            "confidence": 82,
            "entry_price": 100,
            "stop_loss": None,
            "take_profit": None,
            "timestamp": timezone.now(),
            "metadata": {},
            "strategy": strategy,
            "configuration": None,
            "symbol": "R_100",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def _market(self):
        return SimpleNamespace(market="Synthetic", sub_market="Synthetic", display_name="Test Index")

    def _account(self):
        return SimpleNamespace(currency="USD", account_type="demo", broker=SimpleNamespace(name="Deriv"))

    def test_live_confirmation_does_not_manufacture_confidence(self):
        now = timezone.now()
        result = _revise_signal(self._signal(), {"quote": 101, "epoch": int(now.timestamp()), "_source": "deriv_public_websocket"}, now, self._market(), self._account())
        self.assertEqual(result["confidence"], 82.0)
        self.assertEqual(result["confidence_source"], "strategy_signal")
        self.assertTrue(result["execution_ready"])

    def test_conflicting_live_price_fails_closed_without_rewriting_confidence(self):
        now = timezone.now()
        result = _revise_signal(self._signal(), {"quote": 99, "epoch": int(now.timestamp()), "_source": "deriv_public_websocket"}, now, self._market(), self._account())
        self.assertEqual(result["confidence"], 82.0)
        self.assertIsNone(result["direction"])
        self.assertFalse(result["execution_ready"])
        self.assertEqual(result["status"], "LIVE_CONFIRMATION_FAILED")

    def test_missing_entry_price_does_not_create_a_confirmation_direction(self):
        now = timezone.now()
        result = _revise_signal(self._signal(entry_price=None), {"quote": 101, "epoch": int(now.timestamp()), "_source": "deriv_public_websocket"}, now, self._market(), self._account())
        self.assertIsNone(result["entry_price"])
        self.assertIsNone(result["direction"])
        self.assertFalse(result["execution_ready"])
        self.assertEqual(result["status"], "LIVE_CONFIRMATION_UNAVAILABLE")

    def test_stale_analysis_is_not_actionable(self):
        now = timezone.now()
        result = _revise_signal(self._signal(timestamp=now - timedelta(seconds=901)), {"quote": 101, "epoch": int(now.timestamp()), "_source": "deriv_public_websocket"}, now, self._market(), self._account())
        self.assertEqual(result["confidence"], 82.0)
        self.assertIsNone(result["direction"])
        self.assertEqual(result["status"], "ANALYSIS_STALE")
        self.assertFalse(result["execution_ready"])


class SignalBaselineIsolationTests(TestCase):
    def test_baselines_are_scoped_to_the_authenticated_user(self):
        User = get_user_model()
        owner = User.objects.create_user(username="signal-owner", password="pass")
        other = User.objects.create_user(username="signal-other", password="pass")
        strategy = Strategy.objects.create(name="Isolation Strategy", slug="isolation-strategy", category="Trend Following")
        owner_config = StrategyConfiguration.objects.create(strategy=strategy, user=owner, symbol="R_100", timeframe="M1")
        other_config = StrategyConfiguration.objects.create(strategy=strategy, user=other, symbol="R_100", timeframe="M1")
        StrategySignal.objects.create(strategy=strategy, configuration=owner_config, symbol="R_100", signal="BUY", confidence=80)
        StrategySignal.objects.create(strategy=strategy, configuration=other_config, symbol="R_100", signal="SELL", confidence=95)
        request = SimpleNamespace(session={}, user=owner)
        baselines = _analysis_baselines(request, ["R_100"], "M1")
        self.assertEqual(baselines["R_100"].configuration.user_id, owner.id)
        self.assertEqual(baselines["R_100"].signal, "BUY")


class StrategySignalsApiIsolationTests(TestCase):
    def test_strategy_signal_endpoint_excludes_other_users(self):
        User = get_user_model()
        owner = User.objects.create_user(username="api-signal-owner", password="pass")
        other = User.objects.create_user(username="api-signal-other", password="pass")
        strategy = Strategy.objects.create(name="API Isolation Strategy", slug="api-isolation-strategy", category="Trend Following")
        owner_config = StrategyConfiguration.objects.create(strategy=strategy, user=owner, symbol="R_100", timeframe="M1")
        other_config = StrategyConfiguration.objects.create(strategy=strategy, user=other, symbol="R_100", timeframe="M1")
        StrategySignal.objects.create(strategy=strategy, configuration=owner_config, symbol="R_100", signal="BUY", confidence=80)
        StrategySignal.objects.create(strategy=strategy, configuration=other_config, symbol="R_100", signal="SELL", confidence=95)
        request = APIRequestFactory().get("/api/strategies/signals/")
        force_authenticate(request, user=owner)
        response = StrategyViewSet.as_view({"get": "signals"})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["signal"], "BUY")
