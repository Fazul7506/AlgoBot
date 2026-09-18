from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase

from apps.market_data.deriv_sync import _market_name
from apps.market_data.signal_views import _trade_context


class DerivMarketClassificationTests(SimpleTestCase):
    def test_boom_and_crash_ranges_use_symbol_identity(self):
        self.assertEqual(
            _market_name(
                {
                    "underlying_symbol": "BOOM150N",
                    "underlying_symbol_name": "Boom 150 Index",
                    "market": "synthetic_index",
                    "submarket": "crash_index",
                }
            ),
            "Boom",
        )
        self.assertEqual(
            _market_name(
                {
                    "underlying_symbol": "CRASH150N",
                    "underlying_symbol_name": "Crash 150 Index",
                    "market": "synthetic_index",
                    "submarket": "crash_index",
                }
            ),
            "Crash",
        )

    def test_volatility_one_second_symbols_use_broker_identity(self):
        self.assertEqual(
            _market_name(
                {
                    "underlying_symbol": "1HZ30V",
                    "underlying_symbol_name": "Volatility 30 (1s) Index",
                    "market": "synthetic_index",
                }
            ),
            "Volatility Indices",
        )


class SignalTradeContextTests(SimpleTestCase):
    def test_live_quote_source_is_public_deriv_market_data(self):
        class Account:
            currency = "USD"
            account_type = "real"
            broker = type("Broker", (), {"name": "Deriv"})()

        class Strategy:
            name = "test-strategy"
            version = "1"
            category = "trend"

        class Signal:
            symbol = "BOOM1000"
            signal = "SELL"
            entry_price = None
            stop_loss = None
            take_profit = None
            timestamp = __import__("django.utils.timezone", fromlist=["now"]).now()
            metadata = {}
            configuration = None
            strategy = Strategy()

        market = type(
            "Market",
            (),
            {
                "market": "Boom",
                "sub_market": "Boom",
                "display_name": "Boom 1000 Index",
            },
        )()
        context = _trade_context(Signal(), market, Account(), "1m")
        self.assertEqual(context["quote_type"], "deriv_public_websocket")
