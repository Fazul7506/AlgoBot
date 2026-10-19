from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase


User = get_user_model()


class BrowserRegistrationProfileTests(TestCase):
    @patch("core.browser_auth._send_verification", return_value=True)
    def test_registration_requires_and_persists_first_and_last_name(self, _send_verification):
        response = self.client.post(
            "/register/",
            {
                "username": "profile-name-user",
                "first_name": "Jordan",
                "last_name": "Example",
                "email": "jordan.example@example.test",
                "password": "Str0ng-test-password!2026",
                "password_confirm": "Str0ng-test-password!2026",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/verify-email/")
        user = User.objects.get(username="profile-name-user")
        self.assertEqual(user.first_name, "Jordan")
        self.assertEqual(user.last_name, "Example")

    def test_registration_rejects_missing_first_or_last_name(self):
        response = self.client.post(
            "/register/",
            {
                "username": "missing-name-user",
                "email": "missing.name@example.test",
                "password": "Str0ng-test-password!2026",
                "password_confirm": "Str0ng-test-password!2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username, first name, last name, email, and password are required.")
        self.assertFalse(User.objects.filter(username="missing-name-user").exists())

    def test_auth_page_removes_deriv_cta_and_keeps_google_sign_in(self):
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Connect Deriv (broker account)")
        self.assertNotContains(response, "BROKER CONNECTION")
        self.assertContains(response, "Continue with Google")

    def test_registration_page_has_live_password_strength_and_match_feedback(self):
        response = self.client.get("/register/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="password-strength-panel"')
        self.assertContains(response, 'id="password-strength-label"')
        self.assertContains(response, 'id="rule-length"')
        self.assertContains(response, 'id="rule-upper"')
        self.assertContains(response, 'id="rule-lower"')
        self.assertContains(response, 'id="rule-number"')
        self.assertContains(response, 'id="rule-symbol"')
        self.assertContains(response, 'id="rule-not-common"')
        self.assertContains(response, 'id="password-match-note"')
        self.assertContains(response, "password.addEventListener('input', updateStrength)")
        self.assertContains(response, "confirm.setCustomValidity(matches ? '' : 'Passwords must match.')")

    def test_login_page_keeps_username_or_email_and_secure_account_copy(self):
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username or email")
        self.assertContains(response, "Your trading workspace, secured")
        self.assertContains(response, "Continue with Google")
