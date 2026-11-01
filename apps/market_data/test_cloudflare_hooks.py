import json
from unittest.mock import AsyncMock, Mock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.market_data.cloudflare_hooks import cloudflare_market_tick, cloudflare_market_symbols


class CloudflareMarketHookTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.headers = {"HTTP_AUTHORIZATION": "Bearer market-secret"}

    @patch.dict("os.environ", {"CLOUDFLARE_MARKET_STREAM_TOKEN": "market-secret"})
    @patch("apps.market_data.cloudflare_hooks.cache")
    @patch("apps.market_data.cloudflare_hooks.MarketDataService")
    @patch("apps.market_data.cloudflare_hooks.get_channel_layer", return_value=Mock(group_send=AsyncMock()))
    def test_valid_tick_is_ingested(self, _layer, service_class, cache):
        symbol_query = Mock()
        symbol_query.exists.return_value = True
        service_class.symbols.catalogue.return_value = symbol_query
        cache.add.return_value = True
        stored_tick = object()
        service_class.return_value.tick_service.ingest.return_value = stored_tick
        service_class.return_value.tick_service.serialize.return_value = {
            "symbol": "R_100", "quote": "123.45", "epoch": 1_800_000_000
        }
        request = self.factory.post(
            "/api/internal/cloudflare/market-tick/",
            data=json.dumps({"tick": {
                "symbol": "R_100", "quote": 123.45, "epoch": 1_800_000_000, "volume": 0
            }}),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_market_tick(request)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(json.loads(response.content)["status"], "ingested")
        service_class.return_value.tick_service.ingest.assert_called_once()

    @patch.dict("os.environ", {"CLOUDFLARE_MARKET_STREAM_TOKEN": "market-secret"})
    def test_unknown_symbol_is_rejected(self):
        with patch("apps.market_data.cloudflare_hooks.MarketDataService") as service_class:
            query = Mock()
            query.exists.return_value = False
            service_class.symbols.catalogue.return_value = query
            request = self.factory.post(
                "/api/internal/cloudflare/market-tick/",
                data=json.dumps({"tick": {
                    "symbol": "UNKNOWN", "quote": 1, "epoch": 1_800_000_000
                }}),
                content_type="application/json",
                **self.headers,
            )
            response = cloudflare_market_tick(request)
        self.assertEqual(response.status_code, 422)

    def test_missing_token_is_rejected(self):
        request = self.factory.post(
            "/api/internal/cloudflare/market-tick/",
            data=json.dumps({"tick": {}}),
            content_type="application/json",
        )
        with patch.dict("os.environ", {"CLOUDFLARE_MARKET_STREAM_TOKEN": ""}):
            response = cloudflare_market_tick(request)
        self.assertEqual(response.status_code, 401)


    @patch.dict("os.environ", {"CLOUDFLARE_MARKET_STREAM_TOKEN": "market-secret"})
    def test_oversized_tick_payload_is_rejected(self):
        request = self.factory.post(
            "/api/internal/cloudflare/market-tick/",
            data=" " * 16_385,
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_market_tick(request)
        self.assertEqual(response.status_code, 413)

    @patch.dict("os.environ", {"CLOUDFLARE_MARKET_STREAM_TOKEN": "market-secret"})
    @patch("apps.market_data.cloudflare_hooks.sync_active_symbols")
    @patch("apps.market_data.cloudflare_hooks.MarketDataService")
    def test_symbol_endpoint_uses_active_deriv_catalogue(self, service_class, _sync):
        query = Mock()
        query.values_list.return_value = ["R_100", "1HZ100V"]
        service_class.symbols.catalogue.return_value = query
        request = self.factory.get(
            "/api/internal/cloudflare/market-symbols/",
            **self.headers,
        )
        response = cloudflare_market_symbols(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["symbols"], ["R_100", "1HZ100V"])

    @patch.dict("os.environ", {"CLOUDFLARE_MARKET_STREAM_TOKEN": "market-secret"})
    @patch("apps.market_data.cloudflare_hooks.cache")
    @patch("apps.market_data.cloudflare_hooks.MarketDataService")
    @patch("apps.market_data.cloudflare_hooks.get_channel_layer", return_value=None)
    def test_exact_queue_redelivery_is_deduplicated(self, _layer, service_class, cache):
        query = Mock()
        query.exists.return_value = True
        service_class.symbols.catalogue.return_value = query
        cache.add.return_value = False
        cache.get.return_value = {
            "status": "ingested",
            "tick": {"symbol": "R_100", "quote": "123.45", "epoch": 1_800_000_000},
        }
        request = self.factory.post(
            "/api/internal/cloudflare/market-tick/",
            data=json.dumps({"tick": {
                "symbol": "R_100", "quote": 123.45, "epoch": 1_800_000_000, "volume": 0
            }}),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_market_tick(request)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(json.loads(response.content)["status"], "duplicate")
        service_class.return_value.tick_service.ingest.assert_not_called()

    @patch.dict("os.environ", {"CLOUDFLARE_MARKET_STREAM_TOKEN": "market-secret"})
    @patch("apps.market_data.cloudflare_hooks.cache")
    @patch("apps.market_data.cloudflare_hooks.MarketDataService")
    def test_in_progress_duplicate_is_retried(self, service_class, cache):
        query = Mock()
        query.exists.return_value = True
        service_class.symbols.catalogue.return_value = query
        cache.add.return_value = False
        cache.get.return_value = {"status": "processing"}
        request = self.factory.post(
            "/api/internal/cloudflare/market-tick/",
            data=json.dumps({"tick": {
                "symbol": "R_100", "quote": 123.45, "epoch": 1_800_000_000, "volume": 0
            }}),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_market_tick(request)
        self.assertEqual(response.status_code, 503)
        service_class.return_value.tick_service.ingest.assert_not_called()

    @patch.dict("os.environ", {"CLOUDFLARE_MARKET_STREAM_TOKEN": "market-secret"})
    @patch("apps.market_data.cloudflare_hooks.cache")
    @patch("apps.market_data.cloudflare_hooks.MarketDataService")
    @patch("apps.market_data.cloudflare_hooks.get_channel_layer", return_value=None)
    def test_missing_channel_layer_returns_retryable_failure(self, _layer, service_class, cache):
        query = Mock()
        query.exists.return_value = True
        service_class.symbols.catalogue.return_value = query
        cache.add.return_value = True
        stored_tick = object()
        service_class.return_value.tick_service.ingest.return_value = stored_tick
        service_class.return_value.tick_service.serialize.return_value = {
            "symbol": "R_100", "quote": "123.45", "epoch": 1_800_000_000
        }
        request = self.factory.post(
            "/api/internal/cloudflare/market-tick/",
            data=json.dumps({"tick": {
                "symbol": "R_100", "quote": 123.45, "epoch": 1_800_000_000, "volume": 0
            }}),
            content_type="application/json",
            **self.headers,
        )
        response = cloudflare_market_tick(request)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content)["status"], "channel_layer_unavailable")
