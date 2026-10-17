"""Regression checks for production browser/API authentication contracts."""
from pathlib import Path
from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class ProductionApiContractTests(SimpleTestCase):
    def test_account_switch_uses_jwt_and_keeps_session_on_token_refresh_retry(self):
        source = (ROOT / "static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("retryHeaders.set('Authorization','Bearer '+retryToken)", source)
        self.assertIn("const isSessionAccountSelectUrl=url=>", source)
        self.assertIn("const isSessionAccountContextUrl=url=>", source)
        self.assertIn("const sessionAccountContext=isSessionAccountContextUrl(url);", source)
        self.assertIn("credentials:sessionAccountContext?'include':'omit'", source)
        self.assertIn("const requestInit={credentials:sessionAccountContext?'include':'omit',...options,headers,cache:'no-store',signal:controller.signal};", source)
        self.assertIn("credentials:sessionAccountContext?'include':'omit',...options,headers:retryHeaders", source)
        self.assertNotIn("CSRF_TOKEN_UNAVAILABLE", source)
        self.assertNotIn("headers.set('X-CSRFToken',csrfToken)", source)
        self.assertNotIn("is_preferred", source)
        self.assertNotIn("is_default", source)

    def test_deriv_oauth_client_id_is_not_compared_to_numeric_app_id(self):
        source = (ROOT / "config/settings/production.py").read_text(encoding="utf-8")
        self.assertNotIn("DERIV_APP_ID != DERIV_OAUTH_CLIENT_ID", source)
        self.assertIn('"DERIV_OAUTH_CLIENT_ID": DERIV_OAUTH_CLIENT_ID', source)
        self.assertIn('"DERIV_APP_ID": DERIV_APP_ID', source)
