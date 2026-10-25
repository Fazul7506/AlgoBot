from pathlib import Path
from unittest import TestCase

from apps.brokers.constants import BROKER_TYPES


class BrokerLogoCoverageTests(TestCase):
    def test_every_supported_broker_type_has_an_explicit_logo_mapping(self):
        root = Path(__file__).resolve().parents[2]
        template = (root / "templates" / "components" / "broker_logo.html").read_text(encoding="utf-8")
        missing = [broker_type for broker_type in BROKER_TYPES if f"'{broker_type}'" not in template]
        self.assertEqual(missing, [], f"Broker logo mappings are missing for: {missing}")

    def test_logo_component_uses_brand_svg_sources_and_official_fallbacks(self):
        root = Path(__file__).resolve().parents[2]
        template = (root / "templates" / "components" / "broker_logo.html").read_text(encoding="utf-8")
        self.assertIn("cdn.simpleicons.org", template)
        self.assertIn("data-fallback-src=", template)
        self.assertIn("metatrader4.com/favicon.ico", template)
