from unittest.mock import AsyncMock, patch

from django.contrib.auth.models import User
from django.test import TestCase


class BrowserOAuthFlowTests(TestCase):
    def test_browser_logout_redirects_and_uses_ui_notification(self):
        user = User.objects.create_user(username="ui-user", password="pass12345")
        self.client.force_login(user)

        response = self.client.post("/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        follow = self.client.get("/")
        self.assertContains(follow, "You have been logged out securely.")

    @patch("core.views_broker_oauth._authorize", new_callable=AsyncMock, return_value={})
    @patch("core.views_broker_oauth.DerivOAuthService.exchange_code_for_token")
    @patch("core.views_broker_oauth.DerivOAuthService.validate_token_response", return_value=(True, None))
    @patch("core.views_broker_oauth.DerivOAuthService.validate_pkce", return_value=(True, None))
    @patch("core.views_broker_oauth.DerivOAuthService.validate_state", return_value=(True, None))
    def test_oauth_never_creates_user_when_deriv_does_not_return_account_identity(
        self, validate_state, validate_pkce, validate_token, exchange, authorize
    ):
        exchange.return_value = (True, {"access_token": "verified-token", "expires_in": 3600}, None)
        session = self.client.session
        session["oauth_state"] = "state"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "https://example.test/callback/"
        session.save()

        response = self.client.get("/callback/?state=state&code=code")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/brokers/connect/")
        self.assertEqual(User.objects.count(), 0)
        self.assertTrue(any("No local user was created" in str(message) for message in response.wsgi_request._messages))
