from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class SharedInstrumentFrontendServiceTests(SimpleTestCase):
    def read(self, path):
        return (ROOT / path).read_text()

    def test_frontend_facade_owns_the_canonical_catalogue_endpoint(self):
        facade = self.read("static/js/core/algobot_services.js")
        self.assertIn("const instruments = Object.freeze({", facade)
        self.assertIn("'/api/market/catalogue/'", facade)
        self.assertIn("forceRefresh ? '?refresh=1' : ''", facade)
        self.assertIn("symbols: rows", facade)

    def test_instrument_dependent_pages_use_the_shared_catalogue_service(self):
        consumers = (
            "static/js/market_watch.js",
            "static/js/trade_history.js",
            "static/js/trading_terminal.js",
            "static/js/analysis_workspace.js",
            "static/js/live_broker_ui.js",
            "static/js/predictions_workspace_fix.js",
            "static/js/enterprise_templates.js",
            "static/js/strategy_builder.js",
            "static/js/backtesting_workspace_fix.js",
        )
        for path in consumers:
            with self.subTest(path=path):
                self.assertIn("AlgoBotServices", self.read(path))
                self.assertIn("instruments", self.read(path))

    def test_trade_history_uses_the_shared_transport_not_the_legacy_api_client(self):
        script = self.read("static/js/trade_history.js")
        self.assertIn("AlgoBotServices.request('trade-history'", script)
        self.assertNotIn("AlgoBotAPI.apiClient", script)

    def test_strategy_and_backtesting_use_shared_request_and_instrument_services(self):
        strategy = self.read("static/js/strategy_builder.js")
        self.assertIn("AlgoBotServices", strategy)
        self.assertIn("instruments", strategy)
        self.assertNotIn("directGet(", strategy)
        self.assertNotIn("fetch(", strategy)
        backtesting = self.read("static/js/backtesting_workspace_fix.js")
        self.assertIn("AlgoBotServices", backtesting)
        self.assertIn("instruments", backtesting)
        self.assertNotIn("fetch(", backtesting)

    def test_workspace_cache_does_not_shadow_the_canonical_catalogue_cache(self):
        prefetch = self.read("static/js/core/workspace_prefetch.js")
        self.assertNotIn("catalogue|broker-capabilities", prefetch)
        frontend = self.read("static/js/core/frontend_data_contract.js")
        self.assertIn("market\\/(?:catalogue|broker-catalogue)", frontend)
        self.assertIn("return 15000", frontend)
