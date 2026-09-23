from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework.test import APIRequestFactory

from core.api_authentication import BrowserSessionAuthentication
from core.middleware.csrf import APIAwareCsrfViewMiddleware
from core.serializers import SubscriptionSerializer, UserProfileSerializer
from apps.execution.serializers import OrderSerializer
from apps.brokers.models import Broker, BrokerAccount
from apps.brokers.serializers import OrderSerializer as BrokerOrderSerializer


class APISecurityHardeningTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="security-user", password="StrongPassword123!")
        self.broker = Broker.objects.create(name="Test Broker", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id="TEST-ACCOUNT",
            status="active", credentials={"account_type": "demo"},
        )

    def test_subscription_serializer_rejects_client_billing_state(self):
        serializer = SubscriptionSerializer(data={"plan":"ENTERPRISE","price_cents":1,"currency":"USD","is_active":True,"provider":"forged"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        for field in ("plan", "price_cents", "is_active", "provider"):
            self.assertNotIn(field, serializer.validated_data)

    def test_profile_serializer_rejects_server_owned_security_state(self):
        serializer = UserProfileSerializer(data={"email_verified":True,"referral_credits":"999999","referral_code":"FORGED","last_login_at":"2030-01-01T00:00:00Z"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        for field in ("email_verified", "referral_credits", "referral_code", "last_login_at"):
            self.assertNotIn(field, serializer.validated_data)

    def test_order_serializer_requires_own_broker_account(self):
        other = get_user_model().objects.create_user(username="other-security-user", password="StrongPassword123!")
        other_account = BrokerAccount.objects.create(user=other, broker=self.broker, account_id="OTHER-ACCOUNT", status="active", credentials={"account_type":"demo"})
        request = APIRequestFactory().post("/api/orders/")
        request.user = self.user
        serializer = OrderSerializer(data={"broker_account":other_account.pk,"symbol":"R_100","direction":"buy","order_type":"market","stake":"1"}, context={"request":request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("broker_account", serializer.errors)

    def test_broker_order_serializer_rejects_server_execution_state(self):
        request = APIRequestFactory().post("/api/orders/")
        request.user = self.user
        serializer = BrokerOrderSerializer(
            data={
                "account": self.account.pk,
                "symbol": "R_100",
                "direction": "buy",
                "order_type": "market",
                "stake": "1",
                "status": "executed",
                "broker_order_id": "FORGED",
                "routing_context": {"account_type": "real"},
                "client_order_id": "CLIENT-TEST-001",
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        for field in ("status", "broker_order_id", "routing_context"):
            self.assertNotIn(field, serializer.validated_data)

    def test_browser_session_authentication_retains_csrf_enforcement(self):
        self.assertTrue(hasattr(BrowserSessionAuthentication(), "enforce_csrf"))

    def test_api_csrf_middleware_does_not_bypass_session_cookie(self):
        client = Client(enforce_csrf_checks=True)
        self.assertTrue(client.login(username="security-user", password="StrongPassword123!"))

        response = client.patch(
            "/api/settings/",
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
