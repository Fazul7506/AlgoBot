from django.test import SimpleTestCase

from .deriv_sync import _market_name


class DerivMarketClassificationTests(SimpleTestCase):
    def test_boom_and_crash_symbols_use_broker_symbol_identity(self):
        self.assertEqual(
            _market_name({"underlying_symbol": "BOOM150N", "underlying_symbol_name": "Boom 150 Index", "market": "synthetic_index"}),
            "Boom",
        )
        self.assertEqual(
            _market_name({"underlying_symbol": "CRASH150N", "underlying_symbol_name": "Crash 150 Index", "market": "synthetic_index"}),
            "Crash",
        )
