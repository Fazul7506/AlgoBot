from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework.test import APIRequestFactory

from core.api_authentication import BrowserSessionAuthentication
from core.serializers import SubscriptionSerializer, UserProfileSerializer
from apps.execution.serializers import OrderSerializer
from apps.brokers.models import Broker, BrokerAccount
from apps.brokers.serializers import OrderSerializer as BrokerOrderSerializer
from apps.risk.models import RiskProfile, RiskRule
from apps.risk.serializers import RiskRuleSerializer
from apps.portfolio.models import Portfolio, PortfolioAllocation, CashFlow
from apps.portfolio.serializers import PortfolioAllocationSerializer, CashFlowSerializer


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

    def test_risk_rule_serializer_rejects_foreign_profile(self):
        other = get_user_model().objects.create_user(username="other-risk-user", password="StrongPassword123!")
        profile = RiskProfile.objects.create(user=other, profile_name="Other")
        request = APIRequestFactory().post("/api/risk/rules/")
        request.user = self.user
        serializer = RiskRuleSerializer(
            data={"profile": profile.pk, "rule_name": "forged", "rule_type": "max_loss", "value": "0.01"},
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("profile", serializer.errors)

    def test_portfolio_writable_relations_reject_foreign_portfolio(self):
        other = get_user_model().objects.create_user(username="other-portfolio-user", password="StrongPassword123!")
        foreign = Portfolio.objects.create(user=other, name="Other Portfolio")
        request = APIRequestFactory().post("/api/portfolio/allocation/")
        request.user = self.user
        allocation = PortfolioAllocationSerializer(
            data={"portfolio": foreign.pk, "symbol": "R_100", "allocation_percent": "10"},
            context={"request": request},
        )
        self.assertFalse(allocation.is_valid())
        self.assertIn("portfolio", allocation.errors)
        cashflow = CashFlowSerializer(
            data={"portfolio": foreign.pk, "deposit": "100"},
            context={"request": request},
        )
        self.assertFalse(cashflow.is_valid())
        self.assertIn("portfolio", cashflow.errors)

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
