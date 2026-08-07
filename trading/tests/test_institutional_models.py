from django.contrib.auth.models import User
from django.test import TestCase
from trading.models import Trade, TradeStateTransition, UserPreferences
from apps.execution.state_machine import TradeStateMachine


class InstitutionalTradingModelTests(TestCase):
    def test_trade_state_machine_persists_transition(self):
        user = User.objects.create_user(username="quant")
        trade = Trade.objects.create(user=user, symbol="R_75", contract_type="CALL", entry_price=1, stake=10, status="NEW")
        result = TradeStateMachine().transition(trade, "VALIDATED", reason="pre-trade checks passed")
        self.assertEqual(result.to_state, "VALIDATED")
        self.assertTrue(TradeStateTransition.objects.filter(trade=trade, to_state="VALIDATED").exists())

    def test_user_preferences_defaults_are_safe(self):
        user = User.objects.create_user(username="risk")
        prefs = UserPreferences.objects.create(user=user)
        self.assertFalse(prefs.trading_enabled)
        self.assertEqual(prefs.default_symbol, "R_75")
