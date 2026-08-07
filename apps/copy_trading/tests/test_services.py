from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.copy_trading.models import SignalProvider, TradingStrategy, StrategySubscription
from apps.copy_trading.services import CopyTradingEngine, MirrorExecutionService, RiskScalingService, AnalyticsService

class CopyTradingServicesTests(TestCase):
    def test_copy_lifecycle_and_analytics(self):
        user = get_user_model().objects.create_user(username='provider')
        follower = get_user_model().objects.create_user(username='follower')
        provider = SignalProvider.objects.create(user=user, display_name='Alpha')
        strategy = TradingStrategy.objects.create(provider=provider, name='Momentum', category='forex')
        sub = StrategySubscription.objects.create(strategy=strategy, follower=follower)
        CopyTradingEngine().stop(sub)
        mirror = MirrorExecutionService().mirror('T-1', sub, allocation=0.5, multiplier=2)
        self.assertEqual(sub.status, 'paused')
        self.assertEqual(mirror.status, 'mirrored')
        self.assertEqual(RiskScalingService().scale(100, 3, max_exposure=250), 250)
        self.assertEqual(AnalyticsService().roi(25, 100), 0.25)
