from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from apps.brokers.models import BrokerAccount, BrokerConnection


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

    @patch("core.views_deriv_oauth_safe._verify_account", return_value=(None, []))
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.exchange_code_for_token")
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_token_response", return_value=(True, None))
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_pkce", return_value=(True, None))
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_state", return_value=(True, None))
    def test_oauth_never_creates_user_when_deriv_does_not_return_account_identity(
        self, validate_state, validate_pkce, validate_token, exchange, verify_account
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
        self.assertTrue(
            any(
                "could not verify the trading account" in str(message)
                for message in response.wsgi_request._messages
            )
        )

    @patch("core.views_deriv_oauth_safe._verify_account")
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.exchange_code_for_token")
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_token_response", return_value=(True, None))
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_pkce", return_value=(True, None))
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_state", return_value=(True, None))
    def test_oauth_persists_selected_account_and_returns_to_broker_management(
        self, validate_state, validate_pkce, validate_token, exchange, verify_account
    ):
        exchange.return_value = (True, {"access_token": "verified-token", "refresh_token": "refresh-token", "expires_in": 3600}, None)
        verify_account.return_value = (
            {"loginid": "CR1234567", "account_type": "demo", "currency": "USD", "balance": 125.5},
            [{"loginid": "CR1234567", "account_type": "demo", "currency": "USD", "balance": 125.5}],
        )
        session = self.client.session
        session["oauth_state"] = "state"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "https://algobot.dpdns.org/callback/"
        session.save()

        response = self.client.get("/callback/?state=state&code=code")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/brokers/marketplace/")
        account = BrokerAccount.objects.get(account_id="CR1234567")
        self.assertEqual(account.status, "active")
        self.assertTrue(account.is_preferred)
        self.assertFalse(BrokerConnection.objects.filter(broker_account=account, status="connected").exists())
