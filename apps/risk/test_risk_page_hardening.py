from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.brokers.models import Broker, BrokerAccount, Order as BrokerOrder
from apps.risk.models import RiskAssessment, RiskProfile


class RiskPageHardeningTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="risk-owner", password="test-password")
        self.other = User.objects.create_user(username="risk-other", password="test-password")
        self.broker = Broker.objects.create(name="Risk Test Broker", broker_type="deriv", status="active")
        self.account = BrokerAccount.objects.create(
            user=self.user, broker=self.broker, account_id="RISK-OWN", status="active",
            credentials={"account_type": "demo"},
        )
        self.other_account = BrokerAccount.objects.create(
            user=self.other, broker=self.broker, account_id="RISK-OTHER", status="active",
            credentials={"account_type": "demo"},
        )

    def test_broker_order_risk_assessments_are_visible_to_their_owner(self):
        own_order = BrokerOrder.objects.create(
            user=self.user, broker=self.broker, account=self.account,
            symbol="R_100", direction="buy", order_type="market", stake=Decimal("1"),
        )
        foreign_order = BrokerOrder.objects.create(
            user=self.other, broker=self.broker, account=self.other_account,
            symbol="R_75", direction="sell", order_type="market", stake=Decimal("1"),
        )
        own = RiskAssessment.objects.create(broker_trade=own_order, risk_score=10, approved=True)
        RiskAssessment.objects.create(broker_trade=foreign_order, risk_score=90, approved=False)
        self.client.force_login(self.user)
        response = self.client.get("/api/risk/assessment/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload.get("results", []) if isinstance(payload, dict) else payload
        self.assertEqual([item["id"] for item in rows], [own.pk])

    def test_risk_profile_rejects_fractional_limits_above_one(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/risk/profile/",
            data={
                "profile_name": "Unsafe profile",
                "risk_level": "moderate",
                "max_risk_per_trade": "1.2",
                "max_daily_loss": "0.04",
                "max_daily_profit": "0.06",
                "max_drawdown": "0.1",
                "max_open_positions": 10,
                "max_exposure": "0.35",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(RiskProfile.objects.filter(user=self.user, profile_name="Unsafe profile").exists())

    def test_risk_rules_reject_negative_values_and_fraction_overflow(self):
        profile = RiskProfile.objects.create(user=self.user, profile_name="Risk profile")
        self.client.force_login(self.user)
        for rule_type, value in (("max_daily_loss", "2"), ("max_open_positions", "-1")):
            with self.subTest(rule_type=rule_type, value=value):
                response = self.client.post(
                    "/api/risk/rules/",
                    data={
                        "profile": profile.pk,
                        "rule_name": "Invalid rule",
                        "rule_type": rule_type,
                        "value": value,
                        "enabled": True,
                        "priority": 100,
                    },
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
