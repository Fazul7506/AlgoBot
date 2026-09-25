from django.contrib.auth import get_user_model
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from .models import Candle, MarketSnapshot, MarketSymbol


class MarketScannerApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="scanner-test", password="test-pass"
        )
        self.broker = Broker.objects.create(
            name="Deriv", broker_type="deriv", status="active", supports_live=True
        )
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="SCANNER-ACCOUNT",
            status="active",
        )
        BrokerConnection.objects.create(
            broker=self.broker,
            broker_account=self.account,
            status="connected",
            last_ping=timezone.now(),
            connected_at=timezone.now(),
        )
        self.client.force_authenticate(self.user)

        self.gainer = MarketSymbol.objects.create(
            symbol="GAIN", display_name="Gainer", market="Derived Indices",
            broker="deriv", is_active=True, is_tradable=True,
        )
        self.loser = MarketSymbol.objects.create(
            symbol="LOSS", display_name="Loser", market="Derived Indices",
            broker="deriv", is_active=True, is_tradable=True,
        )
        self.no_data = MarketSymbol.objects.create(
            symbol="NODATA", display_name="No Data", market="Derived Indices",
            broker="deriv", is_active=True, is_tradable=True,
        )
        self.other_broker = MarketSymbol.objects.create(
            symbol="OTHER", display_name="Other Broker", market="Forex",
            broker="paper", is_active=True, is_tradable=True,
        )

        now = timezone.now()
        MarketSnapshot.objects.create(
            symbol=self.gainer, last_price=101, high=105, low=95,
            change=1, change_percent=2.5, spread=.2, volume=100, timestamp=now,
        )
        MarketSnapshot.objects.create(
            symbol=self.loser, last_price=99, high=104, low=90,
            change=-1, change_percent=-3.0, spread=.4, volume=80, timestamp=now,
        )
        Candle.objects.bulk_create([
            Candle(
                symbol=self.gainer, timeframe="1m", open=i, high=i + 1,
                low=i - 1, close=i, volume=100, epoch=1_700_000_000 + i * 60,
                source="deriv_candles",
            )
            for i in range(1, 61)
        ])
        Candle.objects.bulk_create([
            Candle(
                symbol=self.loser, timeframe="1m", open=i, high=i + 1,
                low=i - 1, close=i, volume=100, epoch=1_800_000_000 + i * 60,
                source="deriv_candles",
            )
            for i in range(1, 21)
        ])

    def test_scanner_returns_backend_snapshot_and_technical_data(self):
        response = self.client.get("/api/market/scanner/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "broker_snapshot_store")
        symbols = [row["symbol"] for row in payload["results"]]
        self.assertIn("GAIN", symbols)
        self.assertIn("LOSS", symbols)
        self.assertIn("NODATA", symbols)
        self.assertNotIn("OTHER", symbols)
        gain = next(row for row in payload["results"] if row["symbol"] == "GAIN")
        self.assertEqual(gain["technical_source"], "persisted_broker_candles")
        self.assertIsNotNone(gain["rsi"])
        loser = next(row for row in payload["results"] if row["symbol"] == "LOSS")
        self.assertEqual(loser["technical_status"], "insufficient_data")

    def test_gainer_filter_excludes_non_positive_change(self):
        response = self.client.get("/api/market/scanner/?direction=gainers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["symbol"] for row in response.json()["results"]], ["GAIN"]
        )

    def test_spread_filter_excludes_symbols_without_a_snapshot(self):
        response = self.client.get("/api/market/scanner/?max_spread=0.25")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["symbol"] for row in response.json()["results"]], ["GAIN"]
        )

    def test_invalid_filters_are_rejected(self):
        self.assertEqual(
            self.client.get("/api/market/scanner/?direction=sideways").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/market/scanner/?sort=unknown").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/market/scanner/?trend=sideways").status_code, 400
        )

    def test_stale_snapshot_is_not_classified_as_current_opportunity(self):
        snapshot = self.gainer.snapshot
        snapshot.timestamp = timezone.now() - timedelta(seconds=61)
        snapshot.save(update_fields=["timestamp"])
        response = self.client.get("/api/market/scanner/?direction=gainers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_scanner_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/market/scanner/").status_code, 401)

    def test_scanner_requires_connected_broker(self):
        BrokerConnection.objects.filter(broker_account=self.account).delete()
        response = self.client.get("/api/market/scanner/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "NO_CONNECTED_BROKER")
