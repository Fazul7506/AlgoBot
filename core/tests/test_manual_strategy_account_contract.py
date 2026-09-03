from pathlib import Path
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]


class ManualStrategyAccountContractTests(SimpleTestCase):
    def test_manual_terminal_submission_never_routes_through_consensus(self):
        source = (ROOT / 'apps' / 'execution' / 'views.py').read_text()
        self.assertIn("ExecutionEngine().place_order(request.user, **data)", source)
        self.assertNotIn("place_consensus_order(request.user", source)
        self.assertIn("'execution_mode': 'manual_command'", source)

    def test_strategy_service_is_the_autonomous_execution_boundary(self):
        source = (ROOT / 'apps' / 'strategies' / 'services.py').read_text()
        self.assertIn('def _auto_execute_if_allowed', source)
        self.assertIn('ExecutionEngine().place_consensus_order(', source)
        self.assertIn("'execution_mode': 'strategy_auto'", source)
        self.assertIn("criteria_passed", source)
        self.assertIn("signal not in {'BUY', 'SELL'}", source)

    def test_preferred_account_is_not_an_api_or_routing_requirement(self):
        context = (ROOT / 'core' / 'account_context.py').read_text()
        broker_views = (ROOT / 'apps' / 'brokers' / 'views.py').read_text()
        broker_services = (ROOT / 'apps' / 'brokers' / 'services.py').read_text()
        serializer = (ROOT / 'apps' / 'brokers' / 'serializers.py').read_text()
        self.assertNotIn('preferred_account_id', context)
        self.assertNotIn('preferred_account_id', broker_views)
        self.assertNotIn('select_default_account', broker_services)
        self.assertNotIn('p.is_preferred', broker_services)
        self.assertIn('return False', serializer)

    def test_all_plans_have_broker_account_capacity(self):
        billing = (ROOT / 'core' / 'billing_entitlements.py').read_text()
        for plan in ('FREE', 'BASIC', 'PRO', 'ENTERPRISE'):
            self.assertIn(f'"{plan}"', billing)
        self.assertIn('broker_accounts', billing)
        self.assertIn('limit_for(plan,metric)', billing)
