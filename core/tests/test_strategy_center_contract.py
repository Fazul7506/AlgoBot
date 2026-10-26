from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch
from django.urls import reverse


@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
@patch("core.permissions.has_authorized_broker_connection", new=lambda user: True)
@patch("core.permissions.has_verified_account_email", new=lambda user: True)
@patch("core.broker_onboarding.has_authorized_broker_connection", new=lambda user: True)
@patch("core.broker_onboarding.has_verified_account_email", new=lambda user: True)
class StrategyCenterContractTests(TestCase):
    def test_strategy_center_starts_from_broker_connection_state(self):
        user = get_user_model().objects.create_user("strategy-owner", "strategy@example.com", "pass")
        self.client.force_login(user)
        response = self.client.get(reverse("strategies_page"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Broker-aware quant engine", content)
        self.assertIn("broker account", content.lower())
        self.assertIn("execution readiness", content.lower())
        self.assertIn("Browse, analyze and deploy proven trading strategies or create your own.", content)
        self.assertIn("Strategy</span>", content)
        self.assertIn("benchmark-dot", content)
        self.assertIn("data-s-performance-chart", content)
        self.assertIn("data-s-comparison", content)
        self.assertIn("data-strategy-filter=\\"ai\\"", content)
        self.assertIn("data-s-selected-deploy", content)

    def test_strategy_dashboard_has_transport_fallback_and_responsive_reference_styles(self):
        from pathlib import Path
        strategy_js = Path("static/js/strategy_center_fix.js").read_text(encoding="utf-8")
        strategy_css = Path("static/css/strategy_center.css").read_text(encoding="utf-8")
        self.assertIn("if (data?.request) return data.request(path)", strategy_js)
        self.assertIn("credentials: 'same-origin'", strategy_js)
        self.assertIn("function sparklineFor(s)", strategy_js)
        self.assertIn("strategy-card-sparkline", strategy_js)
        self.assertIn("strategy-card-sparkline", strategy_css)
        self.assertIn("@media(max-width:850px)", strategy_css)
        self.assertIn("@media(max-width:580px)", strategy_css)
