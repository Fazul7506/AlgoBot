import re
from urllib.parse import parse_qs, urlparse
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from unittest.mock import patch

from apps.brokers.models import Broker, BrokerAccount, BrokerConnection
from core.account_context import SESSION_KEY
from core.models import UserProfile


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
    BREVO_API_KEY="",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
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
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"email_verified": True, "email_verified_at": timezone.now()},
        )
        response = self.client.post("/api/auth/login/", {
            "identifier": "MAIL@EXAMPLE.COM",
            "password": "A-Strong-Password-2026!",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], user.pk)
        self.assertIn("access", response.json())
        self.assertTrue(response.json()["broker_setup_required"])
        self.assertEqual(response.json()["next_url"], "/brokers/marketplace/")

    def test_password_api_login_rejects_unverified_account(self):
        get_user_model().objects.create_user(
            username="unverified-api-user",
            email="unverified@example.com",
            password="A-Strong-Password-2026!",
        )
        response = self.client.post("/api/auth/login/", {
            "identifier": "unverified@example.com",
            "password": "A-Strong-Password-2026!",
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("access", response.json())

    def test_simplejwt_token_endpoint_accepts_email_identifier(self):
        user = get_user_model().objects.create_user(
            username="token-mail-user", email="token@example.com", password="A-Strong-Password-2026!"
        )
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"email_verified": True, "email_verified_at": timezone.now()},
        )
        response = self.client.post("/api/auth/token/", {
            "email": "TOKEN@EXAMPLE.COM",
            "password": "A-Strong-Password-2026!",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())
        self.assertTrue(response.json()["broker_setup_required"])
        self.assertEqual(response.json()["next_url"], "/brokers/marketplace/")

    def test_refresh_token_requires_verified_email_and_reports_broker_setup(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        user = get_user_model().objects.create_user(
            username="verified-refresh-user",
            email="verified-refresh@example.com",
            password="A-Strong-Password-2026!",
        )
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"email_verified": True, "email_verified_at": timezone.now()},
        )
        refresh = RefreshToken.for_user(user)
        response = self.client.post(
            "/api/auth/token/refresh/", {"refresh": str(refresh)}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
        self.assertTrue(response.json()["broker_setup_required"])
        self.assertEqual(response.json()["next_url"], "/brokers/marketplace/")

    def test_refresh_token_rejects_unverified_account(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        user = get_user_model().objects.create_user(
            username="unverified-refresh-user",
            email="unverified-refresh@example.com",
            password="A-Strong-Password-2026!",
        )
        refresh = RefreshToken.for_user(user)
        response = self.client.post(
            "/api/auth/token/refresh/", {"refresh": str(refresh)}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access", response.json())

    def test_api_logout_revokes_only_the_authenticated_users_refresh_token(self):
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import RefreshToken

        user = get_user_model().objects.create_user(
            username="logout-owner", email="logout@example.com", password="A-Strong-Password-2026!"
        )
        other = get_user_model().objects.create_user(
            username="logout-other", email="other@example.com", password="A-Strong-Password-2026!"
        )
        refresh = RefreshToken.for_user(user)
        other_refresh = RefreshToken.for_user(other)
        response = self.client.post(
            "/api/auth/logout/",
            {"refresh": str(refresh)},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}",
        )
        self.assertEqual(response.status_code, 205)
        with self.assertRaises(TokenError):
            RefreshToken(str(refresh))
        self.assertEqual(str(RefreshToken(str(other_refresh))["user_id"]), str(other.pk))

    def test_password_change_blacklists_refresh_tokens(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

        user = get_user_model().objects.create_user(
            username="password-change-user", email="change@example.com", password="Old-Password-2026!"
        )
        refresh = RefreshToken.for_user(user)
        response = self.client.post(
            "/api/auth/change-password/",
            {
                "old_password": "Old-Password-2026!",
                "new_password": "New-Password-2026!$",
                "new_password_confirm": "New-Password-2026!$",
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(OutstandingToken.objects.filter(user=user).count(), 0)
        self.assertEqual(
            BlacklistedToken.objects.filter(token__user=user).count(),
            OutstandingToken.objects.filter(user=user).count(),
        )

    def test_password_reset_is_single_use_and_updates_password(self):
        user = get_user_model().objects.create_user(
            username="reset-user", email="reset@example.com", password="Old-Password-2026!"
        )
        response = self.client.post("/forgot-password/", {"email": "RESET@example.com"})
        self.assertEqual(response.status_code, 302, (response.context[-1].get("errors") if response.context else response.content.decode("utf-8", errors="replace")[:1200]))
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"/reset-password/([^/\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        raw_token = match.group(1).strip()
        self.assertTrue(raw_token, "password-reset email did not contain a token")
        reset_get = self.client.get(f"/reset-password/{raw_token}/")
        self.assertEqual(reset_get.status_code, 200, f"password-reset GET redirected to {reset_get.headers.get('Location')!r}")

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

    def test_password_reset_blacklists_existing_refresh_tokens(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

        user = get_user_model().objects.create_user(
            username="reset-revoke-user", email="reset-revoke@example.com",
            password="Old-Password-2026!",
        )
        refresh = RefreshToken.for_user(user)
        from core.models import PasswordResetToken
        import hashlib
        raw_token = "one-time-reset-token"
        PasswordResetToken.objects.create(
            user=user,
            token=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        response = self.client.post(f"/reset-password/{raw_token}/", {
            "password": "New-Password-2026!$",
            "password_confirm": "New-Password-2026!$",
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(OutstandingToken.objects.filter(user=user).count(), 0)
        self.assertEqual(
            BlacklistedToken.objects.filter(token__user=user).count(),
            OutstandingToken.objects.filter(user=user).count(),
        )

    def test_profile_api_serializer_cannot_forge_mfa_or_verified_channel_state(self):
        from core.serializers import UserProfileSerializer
        serializer = UserProfileSerializer(data={
            "two_factor_enabled": True,
            "telegram_chat_id": "attacker-controlled",
            "telegram_username": "attacker-controlled",
            "brevo_sender_email": "attacker@example.com",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("two_factor_enabled", serializer.validated_data)
        self.assertNotIn("telegram_chat_id", serializer.validated_data)
        self.assertNotIn("telegram_username", serializer.validated_data)
        self.assertNotIn("brevo_sender_email", serializer.validated_data)

    @patch("core.browser_auth.allow_auth_attempt", return_value=True)
    def test_registration_sends_verification_and_verification_is_single_use(self, _allow_auth_attempt):
        response = self.client.post("/register/", {
            "username": "verify-user",
            "email": "verify@example.com",
            "password": "A-Strong-Password-2026!",
            "password_confirm": "A-Strong-Password-2026!",
        })
        response_details = response.context[-1].get("errors") if response.status_code == 200 and response.context else response.content.decode("utf-8", errors="replace")[:1600] if response.status_code == 200 else None
        if response.status_code != 302:
            response_messages = list(response.context[-1].get("messages", [])) if response.context else []
            user_created = get_user_model().objects.filter(username="verify-user").exists()
            self.fail(
                f"registration rejected: status={response.status_code}; errors={response_details!r}; "
                f"messages={response_messages!r}; user_created={user_created}"
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"/verify-email/\?token=([^\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        raw_token = parse_qs(urlparse(match.group(0)).query).get("token", [""])[0].strip()
        response = self.client.get(f"/verify-email/?token={raw_token}")
        self.assertEqual(response.status_code, 200, f"verification GET redirected to {response.headers.get('Location')!r}; token_present={bool(raw_token)}")
        self.assertContains(response, "Confirm email verification")
        profile = UserProfile.objects.get(user__username="verify-user")
        self.assertFalse(profile.email_verified)
        response = self.client.post("/verify-email/", {"token": raw_token})
        self.assertEqual(response.status_code, 302, f"email verification confirmation failed: status={response.status_code}; body={response.content.decode('utf-8', errors='replace')[:1800]!r}")
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


@override_settings(CREDENTIALS_ENCRYPTION_KEY="test-only-fernet-key")
class BrokerAccountEndpointSafetyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="broker-safety-user", email="broker-safety@example.com",
            password="A-Strong-Password-2026!",
        )
        self.broker = Broker.objects.create(
            name="Deriv", broker_type="deriv", status="active", supports_demo=True, supports_live=True
        )

    def make_account(self, account_id):
        account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id=account_id,
            status="active", token_status="active",
            credentials={"account_type": "demo"},
        )
        account.set_access_token("access-token-for-test")
        account.set_refresh_token("refresh-token-for-test")
        account.save(update_fields=["access_token", "refresh_token"])
        BrokerConnection.objects.create(
            broker=self.broker, broker_account=account, status="connected"
        )
        return account

    def test_deriv_account_endpoints_are_registered(self):
        from django.urls import reverse
        self.assertEqual(reverse("deriv_disconnect"), "/api/deriv/disconnect/")
        self.assertEqual(reverse("deriv_refresh_token"), "/api/deriv/refresh-token/")
        self.assertEqual(reverse("deriv_account_status"), "/api/deriv/status/")
        self.assertEqual(reverse("deriv_reconnect"), "/api/deriv/reconnect/")

    def test_disconnect_requires_explicit_choice_when_user_has_multiple_accounts(self):
        first = self.make_account("CR111111")
        second = self.make_account("CR222222")
        self.client.force_login(self.user)

        response = self.client.post("/api/deriv/disconnect/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, "active")
        self.assertEqual(second.status, "active")
        self.assertEqual(first.get_access_token(), "access-token-for-test")
        self.assertEqual(second.get_access_token(), "access-token-for-test")

    def test_explicit_disconnect_clears_local_tokens_and_connection_state(self):
        account = self.make_account("CR333333")
        self.client.force_login(self.user)

        response = self.client.post(
            "/api/deriv/disconnect/", {"broker_account_id": account.account_id}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertEqual(account.status, "disabled")
        self.assertEqual(account.token_status, "revoked")
        self.assertEqual(account.access_token, "")
        self.assertEqual(account.refresh_token, "")
        self.assertEqual(account.get_access_token(), "")
        self.assertEqual(account.get_refresh_token(), "")
        connection = BrokerConnection.objects.get(broker_account=account)
        self.assertEqual(connection.status, "disconnected")
        self.assertIsNone(connection.last_ping)

    def test_session_selection_disconnects_only_the_selected_account(self):
        first = self.make_account("CR444444")
        second = self.make_account("CR555555")
        self.client.force_login(self.user)
        session = self.client.session
        session[SESSION_KEY] = second.pk
        session.save()

        response = self.client.post("/api/deriv/disconnect/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, "active")
        self.assertEqual(second.status, "disabled")
        self.assertEqual(first.get_access_token(), "access-token-for-test")
        self.assertEqual(second.get_access_token(), "")
        self.assertNotIn(SESSION_KEY, self.client.session)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
    BREVO_API_KEY="",
)
class AccountIdentityManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="identity-user", email="old-address@example.com",
            password="A-Strong-Password-2026!",
        )
        self.profile = UserProfile.objects.get(user=self.user)
        self.client.force_login(self.user)

    def test_username_change_requires_current_password_and_is_persisted(self):
        response = self.client.post("/account/identity/", {
            "current_password": "A-Strong-Password-2026!",
            "username": "identity-user-updated",
            "email": "old-address@example.com",
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "identity-user-updated")
        self.assertEqual(self.user.email, "old-address@example.com")

    def test_email_change_waits_for_verification_of_new_address(self):
        response = self.client.post("/account/identity/", {
            "current_password": "A-Strong-Password-2026!",
            "username": "identity-user",
            "email": "new-address@example.com",
        })
        response_errors = None
        if response.status_code == 200:
            response_errors = response.context[-1].get("errors") if getattr(response, "context", None) else response.content.decode("utf-8", errors="replace")[:1600]
        if response.status_code != 302:
            current_password_valid = self.user.check_password("A-Strong-Password-2026!")
            authenticated_user_id = self.client.session.get("_auth_user_id")
            response_messages = list(response.context[-1].get("messages", [])) if response.context else []
            self.fail(
                f"email change rejected: status={response.status_code}; errors={response_errors!r}; "
                f"current_password_valid={current_password_valid}; authenticated={authenticated_user_id}; "
                f"messages={response_messages}"
            )
        self.assertEqual(response.status_code, 302, f"email change response details: {response_errors!r}; body={response.content.decode('utf-8', errors='replace')[:1600]!r}")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old-address@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new-address@example.com"])
        match = re.search(r"/verify-email/\?token=([^\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        raw_token = parse_qs(urlparse(match.group(0)).query).get("token", [""])[0].strip()

        response = self.client.get(f"/verify-email/?token={raw_token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.email, "old-address@example.com")
        response = self.client.post("/verify-email/", {"token": raw_token})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.email, "new-address@example.com")
        self.assertTrue(self.profile.email_verified)
        self.assertEqual(self.profile.email_verification_token, "")

    def test_email_change_rejects_an_address_owned_by_another_user(self):
        get_user_model().objects.create_user(
            username="other-email-owner", email="owned@example.com",
            password="A-Strong-Password-2026!",
        )
        response = self.client.post("/account/identity/", {
            "current_password": "A-Strong-Password-2026!",
            "username": "identity-user",
            "email": "OWNED@example.com",
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old-address@example.com")
        self.assertContains(response, "already registered")
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_current_password_prevents_identity_changes(self):
        response = self.client.post("/account/identity/", {
            "current_password": "wrong-password",
            "username": "identity-user-taken-over",
            "email": "new-address@example.com",
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "identity-user")
        self.assertEqual(self.user.email, "old-address@example.com")
        self.assertEqual(len(mail.outbox), 0)
