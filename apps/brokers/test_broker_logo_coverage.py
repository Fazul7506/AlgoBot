from pathlib import Path
from unittest import TestCase

from apps.brokers.constants import BROKER_TYPES


class BrokerLogoCoverageTests(TestCase):
    def test_every_supported_broker_type_has_an_explicit_logo_mapping(self):
        root = Path(__file__).resolve().parents[2]
        template = (root / "templates" / "components" / "broker_logo.html").read_text(encoding="utf-8")
        missing = [broker_type for broker_type in BROKER_TYPES if f"'{broker_type}'" not in template]
        self.assertEqual(missing, [], f"Broker logo mappings are missing for: {missing}")

    def test_demo_and_real_account_switcher_uses_svg_mapping_for_every_broker(self):
        root = Path(__file__).resolve().parents[2]
        live_ui = (root / "static" / "js" / "live_broker_ui.js").read_text(encoding="utf-8")
        mapping = live_ui.split("const BROKER_SVG={", 1)[1].split("};", 1)[0]
        missing = [broker_type for broker_type in BROKER_TYPES if f"{broker_type}:" not in mapping]
        self.assertEqual(missing, [], f"Account switcher SVG mappings are missing for: {missing}")
        self.assertNotIn("broker-svg-fallback", live_ui)
        self.assertIn("window.AlgoBotBrokerBranding", live_ui)
        self.assertIn("flagcdn.com", live_ui)
        self.assertIn("identityMarkup", live_ui)
        self.assertIn("https://flagcdn.com/", live_ui)
        self.assertNotIn("name[0]?.toUpperCase()", live_ui)

    def test_logo_component_uses_brand_svg_sources_without_generic_or_text_fallbacks(self):
        root = Path(__file__).resolve().parents[2]
        template = (root / "templates" / "components" / "broker_logo.html").read_text(encoding="utf-8")
        self.assertIn("cdn.simpleicons.org", template)
        self.assertNotIn("data-fallback-src=", template)
        self.assertNotIn("Generic broker symbol", template)
        self.assertNotIn("safe(name[0]?.toUpperCase()", Path(__file__).resolve().parents[2].joinpath("static/js/live_broker_ui.js").read_text(encoding="utf-8"))
        self.assertIn("mt4", template)
        self.assertNotIn("Generic broker symbol", template)

    def test_topbar_account_switcher_uses_same_broker_and_country_svg_assets(self):
        root = Path(__file__).resolve().parents[2]
        topbar = (root / "static" / "js" / "topbar_security_controls.js").read_text(encoding="utf-8")
        self.assertIn("accountIdentity(a)", topbar)
        self.assertIn("AlgoBotBrokerBranding?.identityMarkup", topbar)
        self.assertIn("accountIdentity(current)", topbar)
        self.assertNotIn("name[0]?.toUpperCase()", topbar)
