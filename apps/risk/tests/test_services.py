from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.risk.sizing import PositionSizingService
from apps.risk.services import KillSwitchService, CircuitBreakerService, MarginService

class RiskServicesTests(TestCase):
    def test_position_sizing_percentage_risk(self):
        self.assertEqual(PositionSizingService().calculate(1000, Decimal('0.02'), 2), Decimal('10.00'))
    def test_kill_switch_activation(self):
        user=get_user_model().objects.create_user('risk@example.com')
        KillSwitchService().activate(user,'test')
        self.assertTrue(KillSwitchService().is_active(user))
    def test_circuit_breaker_latency(self):
        self.assertTrue(CircuitBreakerService().evaluate(latency_ms=1500)['active'])
    def test_margin_warning(self):
        self.assertTrue(MarginService().snapshot(100,150)['margin_call'])
