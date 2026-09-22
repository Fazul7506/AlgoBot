from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicSessionUiContractTests(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_public_shell_marks_authentication_state(self):
        base = self.read("templates/base.html")
        self.assertIn('data-authenticated="{% if request.user.is_authenticated %}true{% else %}false{% endif %}"', base)

    def test_public_pages_do_not_prefetch_workspace_accounts(self):
        script = self.read("static/js/core/workspace_prefetch.js")
        self.assertIn("if (document.body?.dataset.authenticated !== 'true') return;", script)
        self.assertIn("const url = '/api/brokers/accounts/';", script)

    def test_frontend_contract_short_circuits_protected_public_requests(self):
        script = self.read("static/js/core/frontend_data_contract.js")
        self.assertIn("protectedPublicPaths", script)
        self.assertIn("error.code='AUTH_REQUIRED'", script)

    def test_api_client_has_same_public_transport_boundary(self):
        script = self.read("static/js/core/api_client.js")
        self.assertIn("protectedPublicPath", script)
        self.assertIn("isSignedOut", script)
        self.assertIn("code:'AUTH_REQUIRED'", script)

    def test_global_shell_suppresses_expected_anonymous_auth_errors(self):
        script = self.read("static/js/base_shell.js")
        self.assertIn("document.body?.dataset.authenticated !== 'true'", script)
        self.assertIn("Number(detail.status) === 401", script)

    def test_money_layer_converts_usd_amounts_but_not_plain_currency_labels(self):
        script = self.read("static/js/core/money_display.js")
        self.assertIn("USD monetary values render with the dollar sign", script)
        self.assertIn("const moneyPattern", script)
        self.assertIn("const suffixPattern", script)
        self.assertIn("deliberately leaving plain currency labels", script)

    def test_money_cache_busting_is_current(self):
        base = self.read("templates/base.html")
        self.assertIn("platform_polish.css' %}?v=20260922-money3", base)
        self.assertIn("api_client.js' %}?v=20260922-public-transport1", base)
        self.assertIn("money_display.js' %}?v=20260922-money2", base)


if __name__ == "__main__":
    unittest.main()
