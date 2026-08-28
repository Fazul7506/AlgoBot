from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class SafeDerivOAuthCallbackTests(TestCase):
    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    def test_provider_error_does_not_restart_oauth_for_anonymous_user(self):
        response = self.client.get(reverse("callback") + "?error=access_denied")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertNotIn("/brokers/connect/", response.url)
        self.assertNotIn("/login/", response.url)
        self.assertNotIn("/dashboard/", response.url)

    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    def test_provider_error_keeps_authenticated_user_in_broker_management(self):
        user = get_user_model().objects.create_user(username="broker-failure-user", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("callback") + "?error=access_denied")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("broker_marketplace_page"))
        self.assertNotIn("/brokers/connect/", response.url)
        self.assertNotIn("/login/", response.url)
        self.assertNotIn("/dashboard/", response.url)

    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    def test_invalid_oauth_state_does_not_restart_oauth_or_open_dashboard(self):
        session = self.client.session
        session["oauth_state"] = "expected-state"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "https://algobot.dpdns.org/callback/"
        session.save()

        response = self.client.get(
            reverse("callback") + "?code=test-code&state=wrong-state"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertNotIn("/brokers/connect/", response.url)
        self.assertNotIn("/login/", response.url)
        self.assertNotIn("/dashboard/", response.url)

    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    @patch("core.views_deriv_oauth_safe._verify_account", return_value=(None, []))
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.exchange_code_for_token", return_value=(True, {"access_token": "token", "expires_in": 3600, "refresh_token": "refresh"}, None))
    def test_authenticated_account_verification_failure_never_redirects_dashboard(self, exchange_token, verify_account):
        user = get_user_model().objects.create_user(username="broker-verification-failure", password="pass12345")
        self.client.force_login(user)
        session = self.client.session
        session["oauth_state"] = "expected-state"
        session["pkce_verifier"] = "verifier"
        session["oauth_redirect_uri"] = "https://algobot.dpdns.org/callback/"
        session.save()

        with patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_state", return_value=(True, "")), patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_pkce", return_value=(True, "")), patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_token_response", return_value=(True, "")):
            response = self.client.get(reverse("callback") + "?code=test-code&state=expected-state")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("broker_marketplace_page"))
        self.assertNotIn("/dashboard/", response.url)
        exchange_token.assert_called_once()
        verify_account.assert_called_once()
