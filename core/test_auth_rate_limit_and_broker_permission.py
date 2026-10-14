from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase

from core.auth_rate_limit import allow_auth_attempt
from core.permissions import BrokerOnboardingRequired
from rest_framework.exceptions import PermissionDenied


User = get_user_model()


class AuthRateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.request = RequestFactory().post("/login/")
        self.request.META["REMOTE_ADDR"] = "192.0.2.10"

    def tearDown(self):
        cache.clear()

    def test_attempts_are_bounded_by_action_ip_and_identity(self):
        self.assertTrue(allow_auth_attempt(self.request, "login", "user@example.test", limit=2, window=60))
        self.assertTrue(allow_auth_attempt(self.request, "login", "user@example.test", limit=2, window=60))
        self.assertFalse(allow_auth_attempt(self.request, "login", "user@example.test", limit=2, window=60))

    def test_different_identities_have_separate_counters(self):
        self.assertTrue(allow_auth_attempt(self.request, "login", "one@example.test", limit=1, window=60))
        self.assertFalse(allow_auth_attempt(self.request, "login", "one@example.test", limit=1, window=60))
        self.assertTrue(allow_auth_attempt(self.request, "login", "two@example.test", limit=1, window=60))


class BrokerOnboardingPermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="permission-user",
            email="permission@example.test",
            password="Test-password-123!secure",
        )

    @patch("core.permissions.has_authorized_broker_connection", return_value=False)
    def test_authenticated_bearer_api_principal_is_denied_without_broker(self, _gate):
        from rest_framework.test import APIRequestFactory

        request = APIRequestFactory().get("/api/orders/")
        request.user = self.user
        with self.assertRaises(PermissionDenied) as raised:
            BrokerOnboardingRequired().has_permission(request, object())
        self.assertEqual(raised.exception.detail["code"], "broker_setup_required")

    @patch("core.permissions.has_authorized_broker_connection", return_value=True)
    def test_eligible_broker_allows_protected_api(self, _gate):
        from rest_framework.test import APIRequestFactory, force_authenticate

        request = APIRequestFactory().get("/api/orders/")
        force_authenticate(request, user=self.user)
        self.assertTrue(BrokerOnboardingRequired().has_permission(request, object()))
