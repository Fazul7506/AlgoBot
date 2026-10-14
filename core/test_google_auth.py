from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

User = get_user_model()


@override_settings(GOOGLE_CLIENT_ID="test-google-client-id", GOOGLE_CLIENT_SECRET="test-google-client-secret")
class GoogleLoginSecurityTests(TestCase):
    def test_callback_rejects_invalid_state_before_token_exchange(self):
        session = self.client.session
        session["algobot_google_login_state"] = "expected-state"
        session["algobot_google_login_started"] = int(timezone.now().timestamp())
        session["algobot_google_login_nonce"] = "expected-nonce"
        session["algobot_google_login_pkce_verifier"] = "pkce-verifier"
        session.save()

        with patch("core.google_auth.requests.post") as token_exchange:
            response = self.client.get("/auth/google/callback/?code=auth-code&state=wrong-state")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")
        token_exchange.assert_not_called()

    @patch("google.oauth2.id_token.verify_oauth2_token")
    @patch("core.google_auth.requests.post")
    def test_valid_google_identity_still_requires_broker_setup(self, token_exchange, verify_id_token):
        session = self.client.session
        session["algobot_google_login_state"] = "expected-state"
        session["algobot_google_login_started"] = int(timezone.now().timestamp())
        session["algobot_google_login_nonce"] = "expected-nonce"
        session["algobot_google_login_pkce_verifier"] = "pkce-verifier"
        session.save()

        token_response = Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {"id_token": "signed-test-id-token"}
        token_exchange.return_value = token_response
        verify_id_token.return_value = {
            "sub": "stable-google-subject",
            "email": "google-user@example.test",
            "email_verified": True,
            "nonce": "expected-nonce",
        }

        response = self.client.get("/auth/google/callback/?code=auth-code&state=expected-state")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/brokers/marketplace/")
        user = User.objects.get(email="google-user@example.test")
        self.assertTrue(user.trading_profile.email_verified)
        self.assertTrue(user.is_authenticated is False)
        verify_id_token.assert_called_once()
        self.assertEqual(token_exchange.call_args.kwargs["data"]["code_verifier"], "pkce-verifier")

    @patch("google.oauth2.id_token.verify_oauth2_token")
    @patch("core.google_auth.requests.post")
    def test_callback_rejects_nonce_mismatch(self, token_exchange, verify_id_token):
        session = self.client.session
        session["algobot_google_login_state"] = "expected-state"
        session["algobot_google_login_started"] = int(timezone.now().timestamp())
        session["algobot_google_login_nonce"] = "expected-nonce"
        session["algobot_google_login_pkce_verifier"] = "pkce-verifier"
        session.save()

        token_response = Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {"id_token": "signed-test-id-token"}
        token_exchange.return_value = token_response
        verify_id_token.return_value = {
            "sub": "stable-google-subject",
            "email": "google-user@example.test",
            "email_verified": True,
            "nonce": "attacker-nonce",
        }

        response = self.client.get("/auth/google/callback/?code=auth-code&state=expected-state")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")
        self.assertFalse(User.objects.filter(email="google-user@example.test").exists())
