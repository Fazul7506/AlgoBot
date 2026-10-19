import hashlib
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import UserProfile
from core.services.two_factor_service import (
    TwoFactorService, generate_recovery_codes, verify_user_code,
)


@override_settings(CREDENTIALS_ENCRYPTION_KEY="test-only-fernet-key")
class TwoFactorEnforcementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="totp-user",
            email="totp-user@example.test",
            password="A-strong-test-password-123!",
        )
        self.secret = TwoFactorService.generate_secret()
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.email_verified = True
        self.profile.email_verified_at = timezone.now()
        self.profile.two_factor_enabled = True
        self.profile.two_factor_secret_encrypted = TwoFactorService.encrypt_secret(self.secret)
        self.profile.save()

    def test_browser_login_requires_and_accepts_authenticator_code(self):
        response = self.client.post("/login/", {
            "identifier": self.user.username,
            "password": "A-strong-test-password-123!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["mfa_required"])
        self.assertNotIn("_auth_user_id", self.client.session)

        code = TwoFactorService(self.secret).get_totp().now()
        response = self.client.post("/login/", {
            "identifier": self.user.username,
            "password": "A-strong-test-password-123!",
            "two_factor_code": code,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(str(self.client.session.get("_auth_user_id")), str(self.user.pk))

    def test_existing_session_is_challenged_after_mfa_is_enabled(self):
        self.client.force_login(self.user)
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login/two-factor/")
        self.assertEqual(str(self.client.session["algobot_pending_2fa_user_id"]), str(self.user.pk))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_api_login_does_not_issue_tokens_without_second_factor(self):
        response = self.client.post("/api/auth/login/", {
            "identifier": self.user.username,
            "password": "A-strong-test-password-123!",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "two_factor_required")
        self.assertNotIn("access", response.json())

    def test_api_login_issues_tokens_only_after_valid_second_factor(self):
        code = TwoFactorService(self.secret).get_totp().now()
        response = self.client.post("/api/auth/login/", {
            "identifier": self.user.username,
            "password": "A-strong-test-password-123!",
            "two_factor_code": code,
        }, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())

    def test_security_center_requires_verified_enrollment_before_enabling_mfa(self):
        self.client.force_login(self.user)
        self.profile.two_factor_enabled = False
        self.profile.two_factor_secret_encrypted = ""
        self.profile.save(update_fields=["two_factor_enabled", "two_factor_secret_encrypted"])
        response = self.client.post("/operations/security/", {
            "security_action": "setup_2fa",
            "current_password": "A-strong-test-password-123!",
        })
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/operations/security/")
        self.assertEqual(response.status_code, 200)
        uri = response.context["two_factor_setup_uri"]
        self.assertTrue(uri.startswith("otpauth://totp/"))
        secret = parse_qs(urlparse(uri).query)["secret"][0]
        code = TwoFactorService(secret).get_totp().now()
        response = self.client.post("/operations/security/", {
            "security_action": "verify_2fa",
            "two_factor_code": code,
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.two_factor_enabled)
        self.assertTrue(self.profile.two_factor_secret_encrypted)
        self.assertEqual(self.profile.two_factor_pending_secret_encrypted, "")
        response = self.client.get("/operations/security/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["two_factor_recovery_codes"]), 10)

    def test_recovery_codes_are_hashed_and_single_use(self):
        codes, hashes = generate_recovery_codes()
        self.assertEqual(len(codes), 10)
        self.assertTrue(all(hashlib.sha256(code.encode("ascii")).hexdigest() in hashes for code in codes))
        self.profile.two_factor_recovery_codes = hashes
        self.profile.save(update_fields=["two_factor_recovery_codes"])
        self.assertTrue(verify_user_code(self.profile, codes[0], consume_recovery=True))
        self.profile.refresh_from_db()
        self.assertNotIn(hashlib.sha256(codes[0].encode("ascii")).hexdigest(), self.profile.two_factor_recovery_codes)
        self.assertFalse(verify_user_code(self.profile, codes[0], consume_recovery=True))
