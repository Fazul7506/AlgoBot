from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse


class SafeDerivOAuthCallbackTests(TestCase):
    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    def test_provider_error_does_not_restart_oauth(self):
        response = self.client.get(reverse("callback") + "?error=access_denied")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertNotIn("/brokers/connect/", response.url)
        self.assertNotIn("/login/", response.url)

    @override_settings(
        DERIV_OAUTH_CLIENT_ID="oauth-client-test",
        DERIV_REDIRECT_URI="https://algobot.dpdns.org/callback/",
    )
    @patch("core.views_deriv_oauth_safe._verify_account", return_value=(None, []))
    def test_invalid_oauth_state_does_not_restart_oauth(self, verify_account):
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
        verify_account.assert_not_called()
