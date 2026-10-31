from django.test import SimpleTestCase

from apps.ai_engine.external_signals import _feed_items, normalize_orderbook


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
