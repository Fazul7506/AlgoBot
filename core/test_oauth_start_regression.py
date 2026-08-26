from unittest.mock import patch

from django.test import TestCase, override_settings


class DerivOAuthStartRegressionTests(TestCase):
    @override_settings(
        DEBUG=False,
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    @patch(
        "core.views.DerivOAuthService.create_authorization_url",
        return_value="https://auth.deriv.test/oauth2/auth?response_type=code",
    )
    def test_broker_connect_persists_oauth_state_and_returns_redirect(self, create_authorization_url):
        response = self.client.get("/brokers/connect/?broker=deriv")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://auth.deriv.test/oauth2/auth?response_type=code")
        self.assertIn("sessionid", response.cookies)

        session = self.client.session
        self.assertEqual(session.get("oauth_state") and len(session["oauth_state"]), 43)
        self.assertEqual(len(session["pkce_verifier"]), 86)
        self.assertEqual(session["oauth_redirect_uri"], "https://algobot.dpdns.org/callback/")
        create_authorization_url.assert_called_once()
