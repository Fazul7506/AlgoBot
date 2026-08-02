from django.test import TestCase
from django.contrib.auth.models import User
from trading.models.copy import CopyFollow, LeaderStats, CopyTrade
from trading.services.copy_service import CopyService
from trading.services.trade_service import TradeService
from trading.models import Trade


class CopyTradingTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user(username='leader', email='leader@example.com', password='password')
        self.follower = User.objects.create_user(username='follower', email='follower@example.com', password='password')
        self.leader_profile = self.leader.trading_profile
        self.follower_profile = self.follower.trading_profile
        self.leader_subscription = self.leader.subscription
        self.follower_subscription = self.follower.subscription
        self.leader_bot = self.leader.bot_settings
        self.follower_bot = self.follower.bot_settings

    def test_follow_and_unfollow(self):
        service = CopyService()
        follow = service.follow(self.leader, self.follower, allocation_type='PERCENT', allocation_value=15.0)

        self.assertIsInstance(follow, CopyFollow)
        self.assertEqual(follow.leader, self.leader)
        self.assertEqual(follow.follower, self.follower)
        self.assertEqual(follow.allocation_type, 'PERCENT')
        self.assertEqual(follow.allocation_value, 15.0)
        self.assertTrue(follow.is_active)

        service.unfollow(self.leader, self.follower)
        follow.refresh_from_db()
        self.assertFalse(follow.is_active)

    def test_handle_leader_trade_creates_copy_trades(self):
        service = CopyService()
        service.follow(self.leader, self.follower, allocation_type='PERCENT', allocation_value=10.0)

        trade = Trade.objects.create(
            user=self.leader,
            strategy='test-strategy',
            symbol='R_100',
            contract_type='CALL',
            entry_price=100.0,
            stake=100.0,
            status='OPEN',
            strategy_confidence=60.0,
            entry_reason='Test open',
            profit=0.0,
            profit_pct=0.0,
            indicators_snapshot={},
            is_paper=True,
        )

        created = service.handle_leader_trade(trade)
        self.assertEqual(len(created), 1)
        self.assertIsInstance(created[0], CopyTrade)
        self.assertEqual(created[0].follower, self.follower)
        self.assertGreater(created[0].amount, 0)
        self.assertEqual(created[0].leader_trade_id, str(trade.id))

    def test_copy_service_uses_fixed_allocation(self):
        service = CopyService()
        service.follow(self.leader, self.follower, allocation_type='FIXED', allocation_value=25.0)

        trade = Trade.objects.create(
            user=self.leader,
            strategy='test-strategy',
            symbol='R_100',
            contract_type='PUT',
            entry_price=120.0,
            stake=200.0,
            status='OPEN',
            strategy_confidence=70.0,
            entry_reason='Test fixed allocation',
            profit=0.0,
            profit_pct=0.0,
            indicators_snapshot={},
            is_paper=True,
        )

        created = service.handle_leader_trade(trade)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].amount, 25.0)

    def test_trade_service_triggers_copy_service(self):
        # Ensure TradeService.open_trade uses CopyService when a leader opens a trade.
        service = CopyService()
        service.follow(self.leader, self.follower, allocation_type='PERCENT', allocation_value=10.0)

        trade_service = TradeService(user=self.leader)
        trade = trade_service.open_trade(
            symbol='R_100',
            signal_direction='BUY',
            entry_price=100.0,
            strategy_name='test-strategy',
            confidence=50,
            market_regime='BULL',
            is_paper=True,
        )

        self.assertIsNotNone(trade)
        copied = CopyTrade.objects.filter(leader_trade_id=str(trade.id), follower=self.follower)
        self.assertTrue(copied.exists())
