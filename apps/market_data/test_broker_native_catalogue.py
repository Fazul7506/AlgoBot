from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from apps.market_data.models import Candle, MarketSymbol, Tick


@patch("core.permissions.has_authorized_broker_connection", new=lambda user: True)
@patch("core.permissions.has_verified_account_email", new=lambda user: True)
@patch("core.permissions.has_authorized_broker_connection", new=lambda user: True)
@patch("core.permissions.has_verified_account_email", new=lambda user: True)
@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
class BrokerNativeCatalogueFallbackTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="catalogue-fallback-user", password="test-pass"
        )
        self.broker = Broker.objects.create(
            name="Deriv", broker_type="deriv", status="active", supports_live=True
        )
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="VRTC-CATALOGUE",
            status="active",
            credentials={"account_type": "demo"},
        )
        BrokerConnection.objects.create(
            broker=self.broker, broker_account=self.account, status="connected"
        )
        MarketSymbol.objects.create(
            broker="deriv",
            symbol="TEST",
            display_name="Test Instrument",
            market="Derived Indices",
            is_active=True,
            is_tradable=True,
        )
        self.client.force_authenticate(self.user)

    @patch(
        "apps.market_data.broker_native._public_deriv",
        side_effect=RuntimeError("provider unavailable"),
    )
    def test_catalogue_serves_last_known_database_symbols_when_deriv_is_unavailable(self, _request):
        market = MarketSymbol.objects.get(symbol="TEST")
        Candle.objects.create(
            symbol=market, timeframe="1m", open="1", high="2", low="1",
            close="2", volume="1", epoch=1790000000, source="deriv_candles",
        )
        Tick.objects.create(symbol=market, quote="2", epoch=1790000060)
        response = self.client.get("/api/market/catalogue/")
        _request.assert_not_called()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["stale"])
        self.assertEqual(response.json()["source"], "cached_broker_catalogue")
        self.assertEqual(response.json()["account_id"], "VRTC-CATALOGUE")
        self.assertEqual(response.json()["symbols"][0]["symbol"], "TEST")
        self.assertIsNone(response.json()["symbols"][0]["exchange_is_open"])
        self.assertIsNone(response.json()["symbols"][0]["is_trading_suspended"])
        self.assertIsNone(response.json()["symbols"][0]["symbol_type"])
        self.assertIn("1m", response.json()["symbols"][0]["supported_timeframes"])
        self.assertEqual(response.json()["symbols"][0]["available_timeframes"], ["tick", "1m"])
        self.assertIn("1h", response.json()["supported_timeframes"])
        self.assertNotIn("1s", response.json()["supported_timeframes"])
        self.assertNotIn("5s", response.json()["supported_timeframes"])

    @patch("apps.market_data.broker_native._schedule_catalogue_sync", return_value=True)
    @patch("apps.market_data.broker_native.sync_active_symbols")
    def test_forced_refresh_uses_background_sync_and_serves_database_catalogue(self, sync_symbols, schedule_sync):
        response = self.client.get("/api/market/catalogue/?refresh=1")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["stale"])
        self.assertTrue(response.json()["refreshing"])
        self.assertEqual(response.json()["source"], "cached_broker_catalogue")
        self.assertEqual(response.json()["symbols"][0]["symbol"], "TEST")
        schedule_sync.assert_called_once_with()
        sync_symbols.assert_not_called()

    @patch("apps.market_data.broker_native._schedule_catalogue_sync", return_value=True)
    @patch("apps.market_data.broker_native.sync_active_symbols")
    def test_refresh_without_new_symbols_keeps_database_catalogue_available(self, sync_symbols, schedule_sync):
        response = self.client.get("/api/market/catalogue/?refresh=1")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["stale"])
        self.assertTrue(response.json()["refreshing"])
        self.assertEqual(response.json()["source"], "cached_broker_catalogue")
        schedule_sync.assert_called_once_with()
        sync_symbols.assert_not_called()

    @patch("apps.market_data.broker_native._schedule_catalogue_sync", return_value=True)
    @patch("apps.market_data.broker_native.sync_active_symbols")
    def test_empty_first_run_schedules_authoritative_sync_without_blocking(self, sync_symbols, schedule_sync):
        MarketSymbol.objects.all().delete()

        response = self.client.get("/api/market/catalogue/")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["code"], "BROKER_CATALOGUE_REFRESHING")
        self.assertEqual(response.json()["symbols"], [])
        self.assertTrue(response.json()["refreshing"])
        schedule_sync.assert_called_once_with()
        sync_symbols.assert_not_called()

    @patch(
        "apps.market_data.broker_native._public_deriv",
        side_effect=RuntimeError("provider unavailable"),
    )
    @patch(
        "apps.market_data.broker_native.cache.get",
    )
    def test_capabilities_serves_last_verified_catalogue_on_transient_provider_failure(self, cache_get, _request):
        cache_get.side_effect = [
            None,
            {
                "symbol": "TEST",
                "contracts": [
                    {
                        "contract_type": "CALL",
                        "contract_category": "callput",
                        "expiry_type": "intraday",
                        "underlying_symbol": "TEST",
                    }
                ],
                "contract_types": ["CALL"],
                "trade_types": ["callput"],
            },
        ]

        from apps.market_data.broker_native import capabilities
        previous_throttles = capabilities.cls.throttle_classes
        capabilities.cls.throttle_classes = []
        try:
            response = self.client.get("/api/market/broker-capabilities/?symbol=TEST")
        finally:
            capabilities.cls.throttle_classes = previous_throttles

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["stale"])
        self.assertEqual(response.json()["source"], "cached_broker_capabilities")
        self.assertEqual(response.json()["contracts"][0]["contract_type"], "CALL")
