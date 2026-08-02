from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.strategies.registry import registry
from apps.strategies.services import StrategyService, StrategyExecutionService
from apps.strategies.models import StrategyConfiguration

class StrategyEngineTests(TestCase):
    def setUp(self): self.user=get_user_model().objects.create_user('s@example.com','s@example.com','pw'); StrategyService().sync_catalog()
    def test_registry_discovers_built_ins(self): self.assertIn('trend_following', registry.all())
    def test_execution_generates_signal(self):
        strategy=StrategyService().sync_catalog()[0]
        config=StrategyConfiguration.objects.create(strategy=strategy,user=self.user,symbol='R_100',timeframe='M1')
        execution=StrategyExecutionService().run_configuration(config, {'price':100,'trend':'up'}, {'rsi':25})
        self.assertEqual(execution.status,'completed'); self.assertIn(execution.signal, ['BUY','SELL','HOLD','STRONG BUY','STRONG SELL','EXIT','REDUCE POSITION','ADD POSITION'])
