from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import UserProfile
from core.services.payment_service import PaymentService
from core.views_broker_oauth import _safe_deriv_identity, sync_deriv_user_identity


class DerivIdentityProjectionTests(TestCase):
    def test_identity_projection_updates_user_profile_and_excludes_secrets(self):
        user = get_user_model().objects.create_user(
            username="deriv_123",
            password="pass12345",
            email="old@example.com",
        )
        profile = UserProfile.objects.get(user=user)

        identity = {
            "user_id": 42,
            "loginid": "CR123456",
            "email": "new@example.com",
            "fullname": "Jane Doe",
            "country": "Kenya",
            "username": "janedoe",
            "access_token": "secret",
            "refresh_token": "secret-refresh",
        }

        safe = sync_deriv_user_identity(user, identity, profile=profile)

        user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertEqual(user.first_name, "Jane")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(profile.country, "Kenya")
        self.assertEqual(safe["username"], "janedoe")
        self.assertNotIn("access_token", safe)
        self.assertNotIn("refresh_token", safe)

    def test_safe_identity_allows_only_non_secret_scalar_identity_fields(self):
        safe = _safe_deriv_identity({
            "user_id": 42,
            "loginid": "CR123456",
            "email": "user@example.com",
            "username": "user",
            "nested": {"secret": "value"},
            "token": "secret",
        })
        self.assertEqual(safe["user_id"], 42)
        self.assertEqual(safe["email"], "user@example.com")
        self.assertNotIn("token", safe)
        self.assertNotIn("nested", safe)


class IntaSendRecurringCustomerValidationTests(TestCase):
    @override_settings(
        INTASEND_PUBLIC_KEY="live-public",
        INTASEND_SECRET_KEY="live-secret",
        INTASEND_API_BASE_URL="https://api.intasend.com",
    )
    @patch("core.services.payment_service.requests.post")
    def test_blank_django_last_name_uses_provider_safe_fallback(self, post):
        def response(payload, status=200):
            result = Mock()
            result.ok = status < 400
            result.status_code = status
            result.headers = {}
            result.json.return_value = payload
            return result

        post.side_effect = [
            response({"id": "customer-1"}),
            response({"id": "plan-1"}),
            response({"id": "subscription-1", "setup_url": "https://payment.intasend.com/subscriptions/charge/test-session"}),
        ]

        user = get_user_model().objects.create_user(
            username="billing-user",
            email="billing@example.com",
            first_name="Billing",
            last_name="",
        )
        plan = SimpleNamespace(plan="BASIC", price_cents=50000, currency="KES", recurring=True)

        result = PaymentService().create_intasend_subscription(user, plan)

        self.assertEqual(result["url"], "https://payment.intasend.com/subscriptions/charge/test-session")
        self.assertEqual(post.call_args_list[0].args[0], "https://api.intasend.com/api/v1/subscriptions-customers/")
        self.assertEqual(post.call_args_list[1].args[0], "https://api.intasend.com/api/v1/subscriptions-plans/")
        self.assertEqual(post.call_args_list[2].args[0], "https://api.intasend.com/api/v1/subscriptions/")
        customer_payload = post.call_args_list[0].kwargs["json"]
        self.assertEqual(customer_payload["first_name"], "Billing")
        self.assertEqual(customer_payload["last_name"], "Customer")


class IntaSendCheckoutUrlHardeningTests(TestCase):
    @override_settings(
        INTASEND_PUBLIC_KEY="live-public",
        INTASEND_SECRET_KEY="live-secret",
        INTASEND_API_BASE_URL="https://api.intasend.com",
    )
    @patch("core.services.payment_service.requests.post")
    def test_recurring_checkout_rejects_wrong_environment_host(self, post):
        def response(payload, status=201):
            result = Mock()
            result.ok = status < 400
            result.status_code = status
            result.headers = {}
            result.json.return_value = payload
            return result

        post.side_effect = [
            response({"id": "customer-1"}),
            response({"id": "plan-1"}),
            response({"id": "subscription-1", "setup_url": "https://api.intasend.com/subscriptions/charge/redacted"}),
        ]
        user = get_user_model().objects.create_user(username="billing-host", email="host@example.com", first_name="Host", last_name="Test")
        plan = SimpleNamespace(plan="BASIC", price_cents=50000, currency="KES", recurring=True)
        result = PaymentService().create_intasend_subscription(user, plan)
        self.assertEqual(result["url"], "")
        self.assertEqual(result["error_classification"], "malformed provider response")

    @override_settings(INTASEND_API_BASE_URL="https://api.intasend.com")
    def test_live_recurring_api_base_honors_configured_endpoint(self):
        service = PaymentService()
        self.assertEqual(service._intasend_subscription_api_base_url(), "https://api.intasend.com")
        self.assertEqual(service.intasend_base_url, "https://api.intasend.com")
