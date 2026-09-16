from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.risk.engine import RiskEngine


class RiskEngineContextTests(TestCase):
    def test_routing_metadata_is_not_passed_to_risk_score(self):
        order = SimpleNamespace(
            pk=1,
            stake=1,
            direction='buy',
            routing_context={},
        )
        assessment = SimpleNamespace(approved=True, rejection_reason='')
        context = {
            'broker_source': 'connected_broker',
            'contract_type': 'market',
            'underlying_symbol': '1HZ100V',
            'execution_mode': 'manual_command',
            'signal_id': None,
            'volatility': 0.10,
        }

        with patch('apps.risk.engine.RiskValidator.validate_order', return_value=True), \
             patch('apps.risk.engine.RiskRepository.assess', return_value=assessment), \
             patch('apps.risk.engine.RiskService.score', return_value=10) as score:
            result = RiskEngine().evaluate_order(order, context)

        self.assertTrue(result.approved)
        score.assert_called_once_with(volatility=0.10)
