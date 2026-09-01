import asyncio
import importlib

from django.test import SimpleTestCase


BROKER_MODULES = (
    "alpaca",
    "binance",
    "bybit",
    "ctrader",
    "dxtrade",
    "exness",
    "forex_com",
    "ic_markets",
    "interactive_brokers",
    "metatrader_gateway",
    "mt4",
)


class UnsupportedBrokerAdapterTests(SimpleTestCase):
    def test_scaffold_adapters_are_not_paper_adapters(self):
        for module_name in BROKER_MODULES:
            module = importlib.import_module(f"apps.brokers.adapters.{module_name}")
            adapter = module.Adapter()
            self.assertFalse(adapter.is_production_ready)
            self.assertFalse(adapter.supports_streaming)
            self.assertNotEqual(adapter.broker_type, "paper")

    def test_scaffold_order_fails_closed(self):
        module = importlib.import_module("apps.brokers.adapters.alpaca")
        adapter = module.Adapter()

        with self.assertRaisesRegex(RuntimeError, "alpaca broker adapter does not implement place_order"):
            asyncio.run(adapter.place_order(object()))
