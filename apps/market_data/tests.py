from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from .constants import TIMEFRAMES
from .historical import persist_candles
from .models import (
    Candle, CandleBackfillRun, CandleBackfillStagedCandle,
    CandleBackfillStagedTick, MarketSymbol, Tick,
)


class BrokerTickApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="market-test", password="test-pass")
        self.broker = Broker.objects.create(name="Deriv", broker_type="deriv", status="active", supports_live=True)
        self.account = BrokerAccount.objects.create(user=self.user, broker=self.broker, account_id="VRTC123", status="active")
        BrokerConnection.objects.create(broker=self.broker, broker_account=self.account, status="connected")
        MarketSymbol.objects.create(symbol="TEST", display_name="Test", market="Derived Indices", is_active=True, is_tradable=True)
        self.client.force_authenticate(self.user)

    def test_broker_tick_accepts_get(self):
        with patch("apps.market_data.api.fetch_tick", return_value={"symbol": "TEST", "quote": 100.25, "epoch": 1}):
            response = self.client.get("/api/market/ticks/broker/?symbol=TEST")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["broker"], "Deriv")
        self.assertEqual(response.json()["account_id"], "VRTC123")
        self.assertFalse(response.json()["stale"])

    def test_broker_tick_accepts_post(self):
        with patch("apps.market_data.api.fetch_tick", return_value={"symbol": "TEST", "quote": 100.25, "epoch": 1}):
            response = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_duplicate_broker_quote_is_idempotent(self):
        quote = {"symbol": "TEST", "quote": 100.25, "bid": 100.20, "ask": 100.30, "epoch": 1787560349, "volume": 0}
        with patch("apps.market_data.api.fetch_tick", return_value=quote):
            first = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
            second = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Tick.objects.filter(symbol__symbol="TEST", epoch=1787560349, quote="100.25000000").count(), 1)

    def test_transient_broker_failure_uses_last_known_quote(self):
        quote = {"symbol": "TEST", "quote": 101.25, "bid": 101.20, "ask": 101.30, "epoch": 1787560350, "volume": 0}
        with patch("apps.market_data.api.fetch_tick", return_value=quote):
            seed = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
        self.assertEqual(seed.status_code, 200)
        with patch("apps.market_data.api.fetch_tick", side_effect=RuntimeError("broker timeout")):
            response = self.client.post("/api/market/ticks/broker/", {"symbol": "TEST"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["stale"])
        self.assertEqual(response.json()["source"], "last_known_broker_quote")
        self.assertEqual(response.json()["quote"], "101.25000000")

    def test_broker_tick_requires_a_symbol(self):
        response = self.client.get("/api/market/ticks/broker/")
        self.assertEqual(response.status_code, 400)


class DataCenterQualityApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="data-center-test", password="test-pass")
        self.client.force_authenticate(self.user)
        self.symbol = MarketSymbol.objects.create(symbol="DC_TEST", display_name="Data Center Test", market="Derived Indices", is_active=True, is_tradable=True)
        self.empty = MarketSymbol.objects.create(symbol="DC_EMPTY", display_name="Empty Symbol", market="Forex", is_active=True, is_tradable=False)

    def test_quality_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/data-center/quality/")
        self.assertEqual(response.status_code, 401)

    def test_quality_reports_tick_and_candle_coverage(self):
        Tick.objects.create(symbol=self.symbol, quote="100.5", epoch=100)
        Candle.objects.create(symbol=self.symbol, timeframe="1m", open="100", high="101", low="99", close="100.5", epoch=100)
        response = self.client.get("/api/data-center/quality/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["summary"]["active_symbols"], 2)
        row = next(item for item in payload["symbols"] if item["symbol"] == "DC_TEST")
        self.assertEqual(row["tick_count"], 1)
        self.assertEqual(row["candle_count"], 1)
        self.assertEqual(row["candle_timeframes"], ["1m"])
        self.assertEqual(row["status"], "healthy")

    def test_quality_marks_old_received_ticks_stale(self):
        Tick.objects.create(symbol=self.symbol, quote="100.5", epoch=100, received_at=timezone.now() - timedelta(minutes=10))
        response = self.client.get("/api/data-center/quality/")
        row = next(item for item in response.json()["symbols"] if item["symbol"] == "DC_TEST")
        self.assertEqual(row["status"], "stale")
        self.assertGreaterEqual(response.json()["summary"]["stale_ticks"], 1)

    def test_quality_marks_empty_symbol_no_data(self):
        response = self.client.get("/api/data-center/quality/")
        row = next(item for item in response.json()["symbols"] if item["symbol"] == "DC_EMPTY")
        self.assertEqual(row["status"], "no_data")


class CandleBackfillStagingTests(TestCase):
    def setUp(self):
        self.symbol = MarketSymbol.objects.create(
            symbol="STAGE_TEST", display_name="Staging Test",
            market="Derived Indices", broker="deriv",
            is_active=True, is_tradable=True,
        )
        self.run = CandleBackfillRun.objects.create(
            scope="research", status="running", count=10, task_id="stage-test-task",
        )

    def test_backfill_candles_are_staged_not_written_to_canonical_table(self):
        result = persist_candles(
            "STAGE_TEST", "1m",
            [{"epoch": 60, "open": "100", "high": "102", "low": "99", "close": "101", "volume": 1}],
            backfill_run_id=self.run.pk,
        )
        self.assertEqual(result["valid"], 1)
        self.assertEqual(Candle.objects.filter(symbol=self.symbol).count(), 0)
        self.assertEqual(
            CandleBackfillStagedCandle.objects.filter(run=self.run, symbol=self.symbol, timeframe="1m").count(),
            1,
        )

    def test_failed_run_delivery_is_rejected_before_work(self):
        from .tasks import _backfill_delivery_guard

        self.run.status = "failed"
        self.run.save(update_fields=["status"])
        allowed, reason = _backfill_delivery_guard(self.run.pk, "stage-test-task")
        self.assertFalse(allowed)
        self.assertEqual(reason, "terminal_failed")

    def _complete_staged_dataset(self):
        for timeframe, seconds in TIMEFRAMES.items():
            epoch = 86400 if seconds == 0 else 86400 - (86400 % seconds)
            CandleBackfillStagedCandle.objects.create(
                run=self.run, symbol=self.symbol, timeframe=timeframe, epoch=epoch,
                open="100", high="102", low="99", close="101", volume="1",
                source="deriv_candles" if seconds >= 60 else "tick_stream",
            )
        CandleBackfillStagedTick.objects.create(
            run=self.run, symbol=self.symbol, quote="101", epoch=86400, volume="0",
        )
        native = {
            timeframe: {"valid": 1}
            for timeframe, seconds in TIMEFRAMES.items()
            if timeframe != "tick" and seconds >= 60
        }
        native["tick-derived"] = {"valid": 1}
        return {"results": {"STAGE_TEST": {"timeframes": native}}}

    def test_promotion_replaces_old_candles_and_ticks_only_after_validation(self):
        from .tasks import _promote_staged_backfill

        old_candle = Candle.objects.create(
            symbol=self.symbol, timeframe="1m", epoch=60,
            open="1", high="1", low="1", close="1",
        )
        old_tick = Tick.objects.create(symbol=self.symbol, quote="1", epoch=60)
        result = self._complete_staged_dataset()

        promoted = _promote_staged_backfill(self.run.pk, result)

        self.assertTrue(promoted["replaced_previous_dataset"])
        self.assertFalse(Candle.objects.filter(pk=old_candle.pk).exists())
        self.assertFalse(Tick.objects.filter(pk=old_tick.pk).exists())
        self.assertEqual(Candle.objects.filter(symbol=self.symbol).count(), len(TIMEFRAMES))
        self.assertEqual(Tick.objects.filter(symbol=self.symbol).count(), 1)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "completed")
        self.assertEqual(self.run.result["dataset_promotion"]["run_id"], self.run.pk)

    def test_failed_promotion_rolls_back_old_dataset(self):
        from unittest.mock import patch
        from .tasks import _promote_staged_backfill

        old_candle = Candle.objects.create(
            symbol=self.symbol, timeframe="1m", epoch=60,
            open="1", high="1", low="1", close="1",
        )
        old_tick = Tick.objects.create(symbol=self.symbol, quote="1", epoch=60)
        result = self._complete_staged_dataset()

        with patch.object(Candle.objects, "bulk_create", side_effect=RuntimeError("simulated insert failure")):
            with self.assertRaises(RuntimeError):
                _promote_staged_backfill(self.run.pk, result)

        self.assertTrue(Candle.objects.filter(pk=old_candle.pk).exists())
        self.assertTrue(Tick.objects.filter(pk=old_tick.pk).exists())
        self.assertTrue(CandleBackfillStagedCandle.objects.filter(run=self.run).exists())
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "running")
