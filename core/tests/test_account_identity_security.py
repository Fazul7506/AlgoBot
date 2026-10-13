import re
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from apps.brokers.models import BrokerAccount
from core.models import UserProfile


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
)
class BrowserAccountAuthenticationTests(TestCase):
    def test_registration_normalizes_email_and_preserves_password_whitespace(self):
        response = self.client.post("/api/auth/register/", {
            "username": "new-account-user",
            "email": " New.User@Example.COM ",
            "password": "  Z7!pQ4m@2026  ",
            "password_confirm": "  Z7!pQ4m@2026  ",
        }, format="json")

        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username="new-account-user")
        self.assertEqual(user.email, "new.user@example.com")
        self.assertTrue(user.check_password("  Z7!pQ4m@2026  "))
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_registration_rejects_case_insensitive_duplicate_email(self):
        get_user_model().objects.create_user(
            username="existing-user", email="user@example.com", password="A-Strong-Password-2026!"
        )
        response = self.client.post("/api/auth/register/", {
            "username": "new-user",
            "email": "USER@EXAMPLE.COM",
            "password": "A-Different-Password-2026!",
            "password_confirm": "A-Different-Password-2026!",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_login_accepts_case_insensitive_email(self):
        user = get_user_model().objects.create_user(
            username="mail-login-user", email="mail@example.com", password="A-Strong-Password-2026!"
        )
        response = self.client.post("/api/auth/login/", {
            "identifier": "MAIL@EXAMPLE.COM",
            "password": "A-Strong-Password-2026!",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], user.pk)
        self.assertIn("access", response.json())

    def test_password_reset_is_single_use_and_updates_password(self):
        user = get_user_model().objects.create_user(
            username="reset-user", email="reset@example.com", password="Old-Password-2026!"
        )
        response = self.client.post("/forgot-password/", {"email": "RESET@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"/reset-password/([^\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        raw_token = match.group(1).strip()
        self.assertEqual(self.client.get(f"/reset-password/{raw_token}/").status_code, 200)

        response = self.client.post(f"/reset-password/{raw_token}/", {
            "password": "New-Password-2026!$",
            "password_confirm": "New-Password-2026!$",
        })
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password("New-Password-2026!$"))
        self.assertFalse(user.check_password("Old-Password-2026!"))
        self.assertEqual(self.client.get(f"/reset-password/{raw_token}/").status_code, 200)
        self.assertContains(self.client.get(f"/reset-password/{raw_token}/"), "invalid, expired, or already used")

    def test_registration_sends_verification_and_verification_is_single_use(self):
        response = self.client.post("/register/", {
            "username": "verify-user",
            "email": "verify@example.com",
            "password": "A-Strong-Password-2026!",
            "password_confirm": "A-Strong-Password-2026!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"/verify-email/\?token=([^\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        raw_token = match.group(1).strip()
        response = self.client.get(f"/verify-email/?token={raw_token}")
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user__username="verify-user")
        self.assertTrue(profile.email_verified)
        self.assertIsNotNone(profile.email_verified_at)
        self.assertEqual(profile.email_verification_token, "")
        self.client.get(f"/verify-email/?token={raw_token}")
        profile.refresh_from_db()
        self.assertTrue(profile.email_verified)


class AnonymousBrokerOAuthFailClosedTests(TestCase):
    @override_settings(DERIV_REDIRECT_URI="https://algobot.example/callback/", DERIV_APP_ID="123", DERIV_AUTH_WS_BASE_URL="wss://ws.example")
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_state", return_value=(True, None))
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_pkce", return_value=(True, None))
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.exchange_code_for_token", return_value=(True, {"access_token": "test-access-token", "expires_in": 3600}, None))
    @patch("core.views_deriv_oauth_safe.DerivOAuthService.validate_token_response", return_value=(True, None))
    @patch("core.views_deriv_oauth_safe._verify_account", return_value=({"account_id": "CR123456", "account_type": "demo"}, [{"account_id": "CR123456", "account_type": "demo"}]))
    @patch("core.views_deriv_oauth_safe.fetch_deriv_identity", side_effect=RuntimeError("provider temporarily unavailable"))
    def test_anonymous_callback_does_not_create_or_log_into_user_when_identity_is_unverified(
        self, fetch_identity, verify_account, validate_token, exchange_token, validate_pkce, validate_state
    ):
        session = self.client.session
        session["oauth_state"] = "expected-state"
        session["pkce_verifier"] = "test-verifier"
        session["oauth_redirect_uri"] = "https://algobot.example/callback/"
        session["oauth_initiating_user_id"] = "__anonymous__"
        session.save()

        response = self.client.get("/callback/?state=expected-state&code=authorization-code")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(BrokerAccount.objects.count(), 0)
        self.assertNotIn("_auth_user_id", self.client.session)
