"""Regression tests for safe post-login browser redirects."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.browser_auth import login_page


class AuthenticatedLoginRedirectTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, pk=42)

    @patch("core.broker_onboarding.has_verified_account_email", return_value=True)
    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=True)
    def test_authenticated_user_is_sent_to_safe_next_destination(self, _broker, _verified):
        request = self.factory.get("/login/?next=%2Ftrading%2F")
        request.user = self.user
        request.session = {}
        response = login_page(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/trading/")

    @patch("core.broker_onboarding.has_verified_account_email", return_value=True)
    @patch("core.broker_onboarding.has_authorized_broker_connection", return_value=True)
    def test_authenticated_user_cannot_redirect_to_external_host(self, _broker, _verified):
        request = self.factory.get("/login/?next=https%3A%2F%2Fevil.example%2Fsteal")
        request.user = self.user
        request.session = {}
        response = login_page(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("dashboard_page"))

    def test_login_page_restores_safe_destination_from_session(self):
        session = self.client.session
        session["broker_onboarding_next"] = "/trading/"
        session.save()

        response = self.client.get(reverse("login_page"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="next" value="/trading/"')
