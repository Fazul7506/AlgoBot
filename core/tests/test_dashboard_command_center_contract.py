from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class DashboardCommandCenterContractTests(SimpleTestCase):
    def test_dashboard_refreshes_on_account_context_changes(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("let loadSeq = 0", source)
        self.assertIn("if (seq !== loadSeq", source)
        self.assertIn("window.addEventListener('algobot:account-changed', accountChanged)", source)
        self.assertIn("window.addEventListener('algobot:account-synced', accountChanged)", source)

    def test_dashboard_financial_values_reject_infinity_and_nan(self):
        source = (ROOT / "static" / "js" / "dashboard_command_center.js").read_text(encoding="utf-8")
        self.assertIn("!Number.isFinite(Number(value))", source)
        self.assertIn("Number.isFinite(Number(item.confidence))", source)
        self.assertIn("item.ask_price ?? item.ask ?? 'Unavailable'", source)
