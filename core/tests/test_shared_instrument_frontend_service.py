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
        )
        for path in consumers:
            with self.subTest(path=path):
                self.assertIn("AlgoBotServices", self.read(path))
                self.assertIn("instruments", self.read(path))

    def test_trade_history_uses_the_shared_transport_not_the_legacy_api_client(self):
        script = self.read("static/js/trade_history.js")
        self.assertIn("AlgoBotServices.request('trade-history'", script)
        self.assertNotIn("AlgoBotAPI.apiClient", script)
