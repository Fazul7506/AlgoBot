"""Regression coverage for preserving the user's explicit Deriv onboarding intent."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import UserProfile


class DerivOnboardingRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="deriv-next-user",
            email="deriv-next@example.test",
            password="Test-password-123!secure",
            first_name="Deriv",
            last_name="User",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"email_verified": True, "email_verified_at": timezone.now(), "terms_accepted_at": timezone.now()},
        )

    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=False)
    def test_password_login_resumes_explicit_deriv_connection(self, _has_connection):
        response = self.client.post(
            "/login/",
            {
                "identifier": self.user.username,
                "password": "Test-password-123!secure",
                "next": "/brokers/connect/?broker=deriv",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/brokers/connect/?broker=deriv")
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_page_has_no_deriv_connect_cta_and_google_defaults_to_dashboard(self):
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sign in, then connect a Deriv trading account")
        self.assertNotContains(response, "Connect Deriv")
        self.assertContains(response, 'href="/auth/google/?next=/dashboard/"')
