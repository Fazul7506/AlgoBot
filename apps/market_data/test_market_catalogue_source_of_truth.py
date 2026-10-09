from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


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
