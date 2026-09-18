from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.analytics.broker_intelligence import build_account_risk_context
from apps.brokers.models import Broker, BrokerAccount
from apps.market_data.models import MarketSymbol
from apps.risk.models import RiskProfile


class BrokerAccountIntelligenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="broker-intel", password="test-pass-123"
        )
        self.broker = Broker.objects.create(
            name="Deriv",
            broker_type="deriv",
            status="active",
            supports_live=True,
        )
        self.account = BrokerAccount.objects.create(
            user=self.user,
            broker=self.broker,
            account_id="CRTEST123",
            currency="USD",
            balance=Decimal("100"),
            equity=Decimal("98"),
            margin=Decimal("20"),
            free_margin=Decimal("78"),
            credentials={"account_type": "demo"},
        )
        RiskProfile.objects.create(
            user=self.user,
            risk_level="moderate",
            max_risk_per_trade=Decimal("0.02"),
            max_daily_loss=Decimal("0.04"),
            max_exposure=Decimal("0.35"),
        )

    def test_sizing_uses_selected_account_and_persisted_risk_profile(self):
        context = build_account_risk_context(
            self.user,
            self.account,
            signal="Strong Bullish",
            confidence=82,
            volatility="normal",
        )
        self.assertEqual(context["account_id"], "CRTEST123")
        self.assertEqual(context["balance"], Decimal("100.00000000"))
        self.assertEqual(context["free_margin"], Decimal("78.00000000"))
        self.assertEqual(context["risk_budget"], Decimal("2.00000000"))
        self.assertEqual(context["recommended_stake"], Decimal("2.00000000"))
        self.assertEqual(context["account_type"], "demo")

    def test_high_volatility_tightens_but_never_increases_user_risk_limit(self):
        context = build_account_risk_context(
            self.user,
            self.account,
            signal="Strong Bullish",
            confidence=82,
            volatility="high",
        )
        self.assertEqual(context["risk_budget"], Decimal("2.00000000"))
        self.assertEqual(context["recommended_stake"], Decimal("1.00000000"))
        self.assertLessEqual(
            Decimal(str(context["recommended_stake"])),
            Decimal(str(context["risk_budget"])),
        )

    @patch("apps.brokers.deriv_execution.DerivTradingOperations.proposal")
    @patch("apps.analytics.views.get_active_account")
    @patch("apps.analytics.views.DerivTradingOperations.proposal")
    @patch("apps.analytics.views.get_active_account")
    @patch("apps.analytics.views.fetch_contracts_for")
    @patch("apps.analytics.views.SynchronizationService.sync_account")
    def test_proposal_endpoint_requires_broker_contract_and_uses_risk_budget(
        self, sync_account, fetch_contracts, get_active, proposal
    ):
        MarketSymbol.objects.create(symbol="R_100", display_name="Volatility 100", market="Volatility Indices")
        get_active.return_value = self.account
        sync_account.return_value = (self.account, {"balance": 100})
        fetch_contracts.return_value = {
            "symbol": "R_100",
            "available_contract_types": ["MULTUP"],
            "available_contract_families": ["multiplier"],
            "expiry_types": ["intraday"],
            "sentiments": ["up"],
        }
        self.client.force_login(self.user)
        response = self.client.post(
            "/analytics/proposal/",
            data={
                "symbol": "R_100",
                "contract_type": "MULTDOWN",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "CONTRACT_NOT_AVAILABLE")
