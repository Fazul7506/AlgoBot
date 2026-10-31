from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class UIRegressionContractTests(SimpleTestCase):
    def test_security_overview_banner_cannot_be_stretched_into_a_narrow_grid_cell(self):
        css = (ROOT / "static/css/security_center.css").read_text(encoding="utf-8")
        self.assertIn("grid-column: 1 / -1", css)
        self.assertIn("align-self: start", css)
        self.assertIn("writing-mode: horizontal-tb", css)

    def test_mobile_notification_popover_is_viewport_bounded_and_scrollable(self):
        css = (ROOT / "static/css/topbar_security_controls.css").read_text(encoding="utf-8")
        self.assertIn("position: fixed !important", css)
        self.assertIn("width: min(410px, calc(100vw - 20px)) !important", css)
        self.assertIn("overflow-y: auto !important", css)

    def test_analysis_grid_children_can_shrink_on_small_screens(self):
        css = (ROOT / "static/css/analysis_reference_redesign.css").read_text(encoding="utf-8")
        self.assertIn(".analysis-dashboard .reference-main-grid > *", css)
        self.assertIn("@media (max-width: 900px)", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", css)

    def test_prediction_market_options_use_valid_html_attributes(self):
        client = (ROOT / "static/js/predictions_workspace_fix.js").read_text(encoding="utf-8")
        self.assertIn('select.innerHTML=\'<option value="">Choose a market</option>\'', client)
        self.assertNotIn('value=\\\\\\"', client)
        self.assertIn("data-ai-catalogue-status", client)
        self.assertIn("Retry instrument list", client)
