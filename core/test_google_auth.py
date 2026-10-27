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
    def test_new_google_signup_redirects_to_profile_completion_before_broker_setup(self, token_exchange, verify_id_token):
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
            "given_name": "Taylor",
            "family_name": "Example",
            "name": "Taylor Example",
        }

        response = self.client.get("/auth/google/callback/?code=auth-code&state=expected-state")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/profile/complete/")
        user = User.objects.get(email="google-user@example.test")
        self.assertEqual(user.first_name, "Taylor")
        self.assertEqual(user.last_name, "Example")
        self.assertTrue(user.trading_profile.email_verified)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        verify_id_token.assert_called_once()
        self.assertEqual(token_exchange.call_args.kwargs["data"]["code_verifier"], "pkce-verifier")

    @patch("google.oauth2.id_token.verify_oauth2_token")
    @patch("core.google_auth.requests.post")
    def test_returning_google_user_with_complete_profile_goes_to_dashboard(self, token_exchange, verify_id_token):
        from core.models import GoogleIdentity, UserProfile

        user = User.objects.create_user(
            username="returning-google-user",
            email="returning-google@example.test",
            password=None,
            first_name="Taylor",
            last_name="Example",
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_verified = True
        profile.email_verified_at = timezone.now()
        profile.terms_accepted_at = timezone.now()
        profile.save(update_fields=["email_verified", "email_verified_at", "terms_accepted_at"])
        GoogleIdentity.objects.create(
            user=user, provider="google", subject="stable-returning-subject",
            email="returning-google@example.test",
        )

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
            "sub": "stable-returning-subject",
            "email": "returning-google@example.test",
            "email_verified": True,
            "nonce": "expected-nonce",
            "given_name": "Taylor",
            "family_name": "Example",
        }

        response = self.client.get("/auth/google/callback/?code=auth-code&state=expected-state")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        self.assertTrue(self.client.session.get("google_existing_login_dashboard"))
        self.assertFalse(self.client.session.get("google_profile_completion_pending"))

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


    @patch("google.oauth2.id_token.verify_oauth2_token")
    @patch("core.google_auth.requests.post")
    def test_authenticated_user_can_explicitly_link_google_identity(self, token_exchange, verify_id_token):
        from core.models import GoogleIdentity, UserProfile

        user = User.objects.create_user(
            username="existing-password-user",
            email="existing-password@example.test",
            password="Local-password-123!secure",
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])
        self.client.force_login(user)

        start_response = self.client.get("/auth/google/?intent=link")
        self.assertEqual(start_response.status_code, 302)
        session = self.client.session
        state = session["algobot_google_login_state"]
        nonce = session["algobot_google_login_nonce"]

        token_response = Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {"id_token": "signed-test-id-token"}
        token_exchange.return_value = token_response
        verify_id_token.return_value = {
            "sub": "explicitly-linked-subject",
            "email": "google-identity@example.test",
            "email_verified": True,
            "nonce": nonce,
        }

        response = self.client.get(f"/auth/google/callback/?code=auth-code&state={state}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/account/identity/")
        identity = GoogleIdentity.objects.get(provider="google", subject="explicitly-linked-subject")
        self.assertEqual(identity.user_id, user.pk)
        self.assertEqual(user.email, "existing-password@example.test")

    def test_google_identity_unlink_requires_local_password_and_removes_link(self):
        from core.models import GoogleIdentity

        user = User.objects.create_user(
            username="unlink-user",
            email="unlink@example.test",
            password="Local-password-123!secure",
        )
        GoogleIdentity.objects.create(
            user=user, provider="google", subject="unlink-subject", email="unlink@example.test"
        )
        self.client.force_login(user)

        response = self.client.post(
            "/account/google/unlink/",
            {"current_password": "Local-password-123!secure"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/account/identity/")
        self.assertFalse(GoogleIdentity.objects.filter(user=user, provider="google").exists())


    def test_google_login_defaults_to_dashboard_without_starting_broker_oauth(self):
        from urllib.parse import parse_qs, urlparse

        response = self.client.get("/auth/google/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        self.assertEqual(
            self.client.session.get("broker_onboarding_next"),
            "/dashboard/",
        )
        params = parse_qs(urlparse(response.url).query)
        self.assertEqual(params.get("code_challenge_method"), ["S256"])
        self.assertTrue(params.get("state"))
        self.assertTrue(params.get("nonce"))

    def test_google_login_preserves_explicit_safe_destination(self):
        response = self.client.get("/auth/google/?next=%2Fsettings%2F")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("broker_onboarding_next"), "/settings/")

    def test_google_login_rejects_external_destination_and_uses_dashboard(self):
        response = self.client.get("/auth/google/?next=https%3A%2F%2Fevil.example%2Fsteal")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session.get("broker_onboarding_next"),
            "/dashboard/",
        )
