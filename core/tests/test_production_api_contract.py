"""Regression checks for production browser/API authentication contracts."""
from pathlib import Path
from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class ProductionApiContractTests(SimpleTestCase):
    def test_account_switch_uses_jwt_and_keeps_session_on_token_refresh_retry(self):
        source = (ROOT / "static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("sessionAccountSelect?'include':'omit'", source)
        self.assertIn("retryHeaders.set('Authorization','Bearer '+retryToken)", source)
        self.assertIn("const isSessionAccountSelectUrl=url=>", source)
        self.assertIn("const sessionAccountSelect=isSessionAccountSelectUrl(url);", source)
        self.assertIn("credentials:sessionAccountSelect?'include':'omit'", source)
        self.assertNotIn("CSRF_TOKEN_UNAVAILABLE", source)
        self.assertNotIn("headers.set('X-CSRFToken',csrfToken)", source)

    def test_deriv_oauth_client_id_is_not_compared_to_numeric_app_id(self):
        source = (ROOT / "config/settings/production.py").read_text(encoding="utf-8")
        self.assertNotIn("DERIV_APP_ID != DERIV_OAUTH_CLIENT_ID", source)
        self.assertIn('"DERIV_OAUTH_CLIENT_ID": DERIV_OAUTH_CLIENT_ID', source)
        self.assertIn('"DERIV_APP_ID": DERIV_APP_ID', source)
