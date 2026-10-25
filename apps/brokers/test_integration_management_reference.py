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



class BrokerMarketplaceRequestAndLogoTests(SimpleTestCase):
    def test_request_broker_uses_styled_inline_form_not_prompts(self):
        template = Path("templates/core/broker_marketplace.html").read_text(encoding="utf-8")
        self.assertIn('data-broker-request-form', template)
        self.assertIn('name="provider_name"', template)
        self.assertIn('data-broker-request-submit', template)
        self.assertNotIn('window.prompt("Which broker', template)
        self.assertNotIn('window.prompt("What markets', template)

    def test_deriv_logo_is_not_placeholder_and_remote_logos_have_first_party_fallbacks(self):
        logo = Path("templates/components/broker_logo.html").read_text(encoding="utf-8")
        deriv = Path("static/icons/brokers/deriv.svg").read_text(encoding="utf-8")
        self.assertIn('aria-label="Deriv"', deriv)
        self.assertIn('>deriv</text>', deriv)
        self.assertNotIn("Trading Platform", deriv)
        self.assertIn('data-provider-name="{{ broker.name|escape }}"', logo)
        marketplace = Path("templates/core/broker_marketplace.html").read_text(encoding="utf-8")
        self.assertIn('img.dataset.fallbackSrc', marketplace)
        self.assertIn('broker-logo-fallback', marketplace)
