from django.test import SimpleTestCase

from .contract import build_contract


class DeveloperContractTests(SimpleTestCase):
    def test_contract_contains_only_registered_developer_routes(self):
        contract = build_contract()
        self.assertEqual(contract["openapi"], "3.0.3")
        self.assertEqual(contract["servers"][0]["url"], "/api/developer")
        self.assertTrue(contract["paths"])
        self.assertTrue(all(path.startswith("/api/developer/") for path in contract["paths"]))

    def test_contract_has_security_schemes(self):
        schemes = build_contract()["components"]["securitySchemes"]
        self.assertIn("ApiKeyAuth", schemes)
        self.assertIn("BearerAuth", schemes)

    def test_contract_does_not_advertise_placeholder_operations(self):
        contract = build_contract()
        text = str(contract["paths"]).lower()
        self.assertNotIn("module ready", text)
        self.assertNotIn("coming soon", text)
        self.assertNotIn("placeholder", text)
