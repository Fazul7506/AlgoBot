from pathlib import Path

from django.test import SimpleTestCase


class AIPredictionsUIContractTests(SimpleTestCase):
    def test_predictions_workspace_uses_shared_authenticated_transport(self):
        script = (Path(__file__).resolve().parents[2] / "static/js/predictions_workspace_fix.js").read_text()
        self.assertIn("window.AlgoBotFrontendData?.request", script)
        self.assertIn("getJSON('/api/market/catalogue/',7000)", script)
        self.assertIn("No synthetic or placeholder candles have been drawn", script)

    def test_predictions_workspace_obeys_global_light_theme_tokens(self):
        script = (Path(__file__).resolve().parents[2] / "static/js/predictions_workspace_fix.js").read_text()
        self.assertIn('html[data-theme="light"] body:has([data-page="core-predictions"])', script)
        for token in ("--ds-surface-1", "--ds-surface-2", "--ds-text", "--ds-muted", "--ds-border", "--ds-accent"):
            self.assertIn(f"var({token}", script)

    def test_empty_model_and_insight_states_are_explicit(self):
        script = (Path(__file__).resolve().parents[2] / "static/js/predictions_workspace_fix.js").read_text()
        self.assertIn("No registered models yet.", script)
        self.assertIn("No verified insights recorded.", script)
        self.assertIn("Model registry unavailable.", script)
