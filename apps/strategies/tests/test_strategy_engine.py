from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.strategies.registry import registry
from apps.strategies.services import StrategyService, StrategyExecutionService
from apps.strategies.models import StrategyConfiguration, StrategySignal

class StrategyEngineTests(TestCase):
    def setUp(self): self.user=get_user_model().objects.create_user('s@example.com','s@example.com','pw'); StrategyService().sync_catalog()
    def test_registry_discovers_built_ins(self): self.assertIn('trend_following', registry.all())
    def test_execution_generates_signal(self):
        strategy=registry.get('trend_following')
        strategy_record=StrategyService().sync_catalog()
        strategy_record=next(item for item in strategy_record if item.slug == 'trend_following')
        config=StrategyConfiguration.objects.create(strategy=strategy_record,user=self.user,symbol='R_100',timeframe='M1')
        execution=StrategyExecutionService().run_configuration(config, {'price':100,'trend':'up'}, {'rsi':25})
        self.assertEqual(execution.status,'completed')
        self.assertEqual(execution.signal, 'BUY')
        self.assertEqual(execution.confidence, 80)
        self.assertEqual(StrategySignal.objects.filter(configuration=config).count(), 1)

