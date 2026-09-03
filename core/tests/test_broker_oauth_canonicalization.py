from unittest.mock import patch

from django.test import TestCase, override_settings


class BrokerOAuthCanonicalizationTests(TestCase):
    @override_settings(
        DEBUG=False,
        ALLOWED_HOSTS=["algobot.example.com", "www.algobot.example.com", "testserver"],
        DERIV_OAUTH_CLIENT_ID="test-client",
        DERIV_REDIRECT_URI="https://algobot.example.com/callback/",
        SESSION_COOKIE_SECURE=True,
    )
    @patch("core.views.DerivOAuthService.validate_configuration", return_value=(True, None))
    @patch("core.views.DerivOAuthService.generate_pkce_pair")
    @patch("core.views.DerivOAuthService.store_oauth_state_in_session")
    def test_oauth_start_redirects_to_canonical_host_before_creating_state(
        self, store_state, generate_pkce, validate_configuration
    ):
        response = self.client.get(
            "/brokers/connect/?broker=deriv",
            HTTP_HOST="www.algobot.example.com",
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://algobot.example.com/brokers/connect/?broker=deriv",
        )
        generate_pkce.assert_not_called()
        store_state.assert_not_called()

    @override_settings(
        DEBUG=False,
        ALLOWED_HOSTS=["algobot.example.com", "www.algobot.example.com", "testserver"],
        DERIV_OAUTH_CLIENT_ID="test-client",
        DERIV_REDIRECT_URI="https://algobot.example.com/callback/",
        SESSION_COOKIE_SECURE=True,
    )
    @patch("core.views.DerivOAuthService.validate_configuration", return_value=(True, None))
    @patch("core.views.DerivOAuthService.generate_pkce_pair")
    @patch("core.views.DerivOAuthService.generate_state", return_value="state")
    @patch("core.views.DerivOAuthService.store_oauth_state_in_session")
    @patch(
        "core.views.DerivOAuthService.create_authorization_url",
        return_value="https://auth.deriv.com/oauth2/auth?state=state",
    )
    def test_oauth_start_creates_state_on_canonical_host(
        self, create_url, store_state, generate_state, generate_pkce, validate_configuration
    ):
        generate_pkce.return_value = ("verifier", "challenge")
        response = self.client.get(
            "/brokers/connect/?broker=deriv",
            HTTP_HOST="algobot.example.com",
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://auth.deriv.com/oauth2/auth?state=state")
        store_state.assert_called_once_with(
            response.wsgi_request, "state", "verifier", "https://algobot.example.com/callback/"
        )
