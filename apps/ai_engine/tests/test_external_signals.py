from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ai_engine.external_signals import (
    _feed_items,
    ingest_orderbook_snapshots,
    normalize_orderbook,
)


class ExternalMarketSignalTests(SimpleTestCase):
    def test_orderbook_imbalance_uses_bid_and_ask_depth(self):
        result = normalize_orderbook({
            "bids": [[100.0, 8.0], [99.9, 2.0]],
            "asks": [[100.1, 5.0], [100.2, 5.0]],
        })
        self.assertAlmostEqual(result["bid_volume"], 10.0)
        self.assertAlmostEqual(result["ask_volume"], 10.0)
        self.assertAlmostEqual(result["imbalance"], 0.0)
        self.assertGreater(result["spread_bps"], 0.0)

    def test_orderbook_imbalance_is_positive_when_bid_depth_dominates(self):
        result = normalize_orderbook({
            "bids": [[100.0, 9.0]],
            "asks": [[100.1, 1.0]],
        })
        self.assertAlmostEqual(result["imbalance"], 0.8)

    def test_orderbook_rejects_missing_depth_instead_of_using_candle_volume(self):
        with self.assertRaises(ValueError):
            normalize_orderbook({"bids": [], "asks": [[100.0, 1.0]]})


    def test_orderbook_ingestion_requires_an_explicit_provider_symbol_allowlist(self):
        with patch.dict(
            "os.environ",
            {
                "ORDER_BOOK_API_URL": "https://provider.example/book/{symbol}",
                "ORDER_BOOK_SYMBOLS": "",
            },
            clear=False,
        ):
            result = ingest_orderbook_snapshots()
        self.assertEqual(result, {"symbols": 0, "snapshots": 0, "configured": 0})

    def test_rss_parser_supports_atom_entries(self):
        payload = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>EUR/USD outlook</title>
          <summary>Markets are optimistic about the currency pair.</summary>
          <link href="https://example.com/story"/>
          <published>2026-10-31T10:00:00Z</published></entry>
        </feed>"""
        rows = _feed_items(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "EUR/USD outlook")
        self.assertEqual(rows[0]["link"], "https://example.com/story")


    def test_sentiment_keyword_catalogue_includes_inactive_and_untradable_symbols(self):
        from apps.ai_engine.external_signals import _catalogue_sentiment_keywords
        with patch("apps.market_data.services.MarketDataService.symbols.catalogue") as catalogue:
            catalogue.return_value.values.return_value.iterator.return_value = iter([
                {"symbol": "R_100", "display_name": "Volatility 100 Index", "market": "synthetic", "sub_market": ""},
                {"symbol": "frxEURUSD", "display_name": "EUR/USD", "market": "forex", "sub_market": ""},
            ])
            keywords = _catalogue_sentiment_keywords()
        self.assertIn("R_100", keywords)
        self.assertIn("frxEURUSD", keywords)
        self.assertIn("EUR/USD", keywords["FRXEURUSD"])

    def test_sentiment_overrides_are_additive_to_catalogue(self):
        from apps.ai_engine.external_signals import sentiment_symbol_keywords
        with patch("apps.ai_engine.external_signals._catalogue_sentiment_keywords", return_value={"R_100": ["R_100"]}), patch.dict(
            "os.environ", {"AI_SENTIMENT_SYMBOL_KEYWORDS_JSON": '{"R_100":["Volatility 100"]}'}
        ):
            keywords = sentiment_symbol_keywords()
        self.assertEqual(set(keywords["R_100"]), {"R_100", "Volatility 100"})

    def test_sentiment_ticker_matching_uses_token_boundaries(self):
        from apps.ai_engine.external_signals import _matches_keyword
        self.assertTrue(_matches_keyword("Bitcoin BTC/USD rises", "BTC"))
        self.assertFalse(_matches_keyword("whether markets rise", "ETH"))

    def test_binance_orderbook_adapter_requires_explicit_symbol_mapping(self):
        from apps.ai_engine.external_signals import BinanceSpotOrderBookAdapter, OrderBookProviderError
        adapter = BinanceSpotOrderBookAdapter({})
        with self.assertRaises(OrderBookProviderError):
            adapter.fetch("CRYBTCUSD")

    def test_orderbook_configuration_rejects_malformed_symbol_map(self):
        from apps.ai_engine.external_signals import _orderbook_symbol_configuration
        with patch.dict("os.environ", {"ORDER_BOOK_PROVIDER": "binance_spot", "ORDER_BOOK_SYMBOLS": "CRYBTCUSD", "ORDER_BOOK_SYMBOL_MAP_JSON": "[]"}):
            with self.assertRaises(RuntimeError):
                _orderbook_symbol_configuration()


    def test_binance_adapter_requests_provider_mapped_level_two_depth(self):
        from apps.ai_engine.external_signals import BinanceSpotOrderBookAdapter
        payload = {"lastUpdateId": 123, "bids": [["100", "2"]], "asks": [["101", "3"]]}
        response = __import__("unittest").mock.Mock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with patch("apps.ai_engine.external_signals.requests.get", return_value=response) as get:
            result = BinanceSpotOrderBookAdapter({"CRYBTCUSD": "BTCUSDT"}).fetch("CRYBTCUSD")
        self.assertEqual(result, payload)
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["params"], {"symbol": "BTCUSDT", "limit": 100})

    def test_orderbook_rejects_non_finite_depth(self):
        with self.assertRaises(ValueError):
            normalize_orderbook({"bids": [[100, float("nan")]], "asks": [[101, 1]]})
