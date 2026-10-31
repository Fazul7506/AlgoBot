from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from .models import MarketSymbol
from .services import MarketDataService


class MarketCatalogueSourceOfTruthTests(SimpleTestCase):
    @patch("apps.market_data.management.commands.seed_markets.sync_active_symbols", return_value=42)
    def test_seed_markets_command_syncs_only_the_live_broker_catalogue(self, sync):
        call_command("seed_markets")
        sync.assert_called_once_with()

    @patch("apps.market_data.management.commands.seed_markets.sync_active_symbols", return_value=0)
    def test_empty_broker_catalogue_fails_without_local_defaults(self, sync):
        with self.assertRaisesRegex(CommandError, "refusing to seed local defaults"):
            call_command("seed_markets")
        sync.assert_called_once_with()

    @patch(
        "apps.market_data.management.commands.seed_markets.sync_active_symbols",
        side_effect=RuntimeError("broker unavailable"),
    )
    def test_broker_failure_fails_closed_without_fallback_symbols(self, sync):
        with self.assertRaisesRegex(CommandError, "no fallback symbols were seeded"):
            call_command("seed_markets")
        sync.assert_called_once_with()

class SymbolServiceCatalogueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_deriv = MarketSymbol.objects.create(
            broker="deriv", symbol="R_10", display_name="Volatility 10 Index",
            market="Volatility Indices", sub_market="Continuous Indices",
            is_active=True, is_tradable=True,
        )
        MarketSymbol.objects.create(
            broker="deriv", symbol="R_25", display_name="Volatility 25 Index",
            market="Volatility Indices", sub_market="Continuous Indices",
            is_active=True, is_tradable=False,
        )
        MarketSymbol.objects.create(
            broker="deriv", symbol="R_50", display_name="Volatility 50 Index",
            market="Volatility Indices", sub_market="Continuous Indices",
            is_active=False, is_tradable=True,
        )
        MarketSymbol.objects.create(
            broker="other", symbol="R_10_ALT", display_name="Other Broker 10",
            market="Volatility Indices", sub_market="Continuous Indices",
            is_active=True, is_tradable=True,
        )

    def test_catalogue_applies_broker_active_and_tradable_scope(self):
        symbols = list(
            MarketDataService.symbols.catalogue(
                broker="DERIV", active=True, tradable=True
            ).values_list("symbol", flat=True)
        )
        self.assertEqual(symbols, ["R_10"])

    def test_catalogue_search_and_market_filters_share_one_query_boundary(self):
        symbols = list(
            MarketDataService.symbols.catalogue(
                broker="deriv", active=True, tradable=None,
                market="volatility indices", search="Volatility 25",
            ).values_list("symbol", flat=True)
        )
        self.assertEqual(symbols, ["R_25"])
