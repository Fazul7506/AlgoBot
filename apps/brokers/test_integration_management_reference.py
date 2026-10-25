from pathlib import Path

from django.test import SimpleTestCase


class BrokerIntegrationManagementReferenceLayoutTests(SimpleTestCase):
    def test_non_reference_request_form_card_is_not_rendered(self):
        template = Path(
            "apps/brokers/templates/brokers/integration_management.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn('id="bi-request"', template)
        self.assertNotIn('name="provider_website"', template)
        self.assertNotIn('name="contact_email"', template)
        self.assertIn('href="#bi-assistant-chat"', template)

    def test_reference_dashboard_sections_and_inline_svg_icons_remain(self):
        template = Path(
            "apps/brokers/templates/brokers/integration_management.html"
        ).read_text(encoding="utf-8")
        for heading in (
            "Broker Integrations",
            "Integration Requests",
            "Recent Pull Requests",
            "Validation Pipeline",
            "Quick Actions",
            "Latest Integration Activity",
            "Recent Chat Activity",
            "AlgoBot Assistant",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, template)
        self.assertIn("<svg", template)
        shared_logo = Path("templates/components/broker_logo.html").read_text(encoding="utf-8")
        for official_asset in (
            "https://deriv.com/favicon.ico",
            "https://www.oanda.com/favicon.ico",
            "https://www.interactivebrokers.com/favicon.ico",
            "https://www.metatrader5.com/favicon.ico",
            "https://www.binance.com/favicon.ico",
            "https://www.kraken.com/favicon.ico",
            "https://www.coinbase.com/favicon.ico",
            "https://www.xtb.com/favicon.ico",
        ):
            with self.subTest(official_asset=official_asset):
                self.assertIn(official_asset, shared_logo)
        self.assertIn("logoFallback", template)
        self.assertIn("grid-template-areas", template)
