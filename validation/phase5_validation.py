#!/usr/bin/env python
"""
Phase 5 Risk Management Engine - Validation Script
Tests risk controls, trade guardrails, stake sizing, and bot-level risk integration.
"""

import os
import sys
from pathlib import Path
import django

# Ensure the project root is importable when running from the validation directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deriv_platform.settings')
django.setup()

from django.contrib.auth.models import User
from django.test import Client
from rest_framework.test import APIClient
from trading.models.core import Strategy, Trade
from trading.services.risk_service import RiskService
from trading.services.trade_service import TradeService
from trading.bot_engine import DerivBotEngine


def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase5Validator:
    """Validates Phase 5 risk engine and execution protections"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        # Clean up any leftover test data
        Strategy.objects.filter(name__in=['risk_test', 'risk_close_test', 'bot_test']).delete()
        Trade.objects.all().delete()
        # Clean up any leftover test data
        Strategy.objects.all().delete()
        Trade.objects.all().delete()

    def test(self, name, func):
        """Run a test and track result"""
        try:
            result = func()
            if result:
                print(f"[PASS] {name}")
                self.passed += 1
            else:
                print(f"[FAIL] {name}")
                self.failed += 1
                self.errors.append(name)
        except Exception as e:
            print(f"[FAIL] {name}: {str(e)}")
            self.failed += 1
            self.errors.append(f"{name}: {str(e)}")

    def validate_imports(self):
        """Test 1: Validate imports for Phase 5 modules"""
        def check():
            from trading.services.risk_service import RiskService
            from trading.services.trade_service import TradeService
            from trading.bot_engine import DerivBotEngine
            from trading.models.core import Strategy, Trade
            return True

        print_section("Testing Imports")
        self.test("Phase 5 imports successful", check)

    def validate_risk_service_basics(self):
        """Test 2: Validate basic risk service behavior"""
        def check():
            risk = RiskService(balance=1000.0, risk_pct=0.02, max_daily_loss_pct=0.05, max_stake_pct=0.1)
            assert risk.get_balance() == 1000.0
            assert risk.calculate_stake() == round(min(1000.0 * 0.02, 1000.0 * 0.1), 2)
            assert risk.get_position_size() == risk.calculate_stake()
            assert risk.get_remaining_daily_risk() == 50.0
            assert risk.get_drawdown_pct() == 0.0
            return True

        print_section("Testing Risk Service Basics")
        self.test("Risk service stake sizing and helpers", check)

    def validate_risk_service_stop_conditions(self):
        """Test 3: Validate the risk service stop conditions"""
        def check():
            risk = RiskService(balance=1000.0, risk_pct=0.02, max_daily_loss_pct=0.05, max_consecutive_losses=2, max_drawdown_pct=0.10)

            risk.daily_loss = 60.0
            if risk.can_trade():
                return False

            risk.daily_loss = 0.0
            risk.consecutive_losses = 2
            if risk.can_trade():
                return False

            risk.consecutive_losses = 0
            risk.balance = 850.0
            if risk.can_trade():
                return False

            return True

        print_section("Testing Risk Service Stop Conditions")
        self.test("Risk engine blocks trading on daily loss, streak loss, and drawdown", check)

    def validate_trade_service_risk_integration(self):
        """Test 4: Validate TradeService integrates with risk rules"""
        def check():
            Strategy.objects.all().delete()
            strategy = Strategy.objects.create(
                name='risk_test',
                strategy_type='TREND',
                description='Risk integration test',
                config={},
                is_active=True,
            )

            risk = RiskService(balance=1000.0, risk_pct=0.05, max_daily_loss_pct=0.01, min_stake=0.35)
            trade_service = TradeService(risk_service=risk)

            trade = trade_service.open_trade(
                symbol='R_75',
                signal_direction='BUY',
                entry_price=1.23,
                strategy_name=strategy.name,
                confidence=50,
                market_regime='trending_up',
            )

            if not trade:
                return False
            if trade.stake > risk.get_remaining_daily_risk():
                return False

            risk.daily_loss = 20.0
            blocked_trade = trade_service.open_trade(
                symbol='R_75',
                signal_direction='SELL',
                entry_price=1.24,
                strategy_name=strategy.name,
            )
            if blocked_trade is not None:
                return False

            return True

        print_section("Testing Trade Service Risk Integration")
        self.test("Trade service enforces risk service and daily risk cap", check)

    def validate_trade_closure_updates_risk(self):
        """Test 5: Validate closing a trade updates risk state"""
        def check():
            Strategy.objects.all().delete()
            strategy = Strategy.objects.create(
                name='risk_close_test',
                strategy_type='TREND',
                description='Risk close test',
                config={},
                is_active=True,
            )

            risk = RiskService(balance=1000.0, risk_pct=0.02, max_daily_loss_pct=0.05)
            trade_service = TradeService(risk_service=risk)

            trade = trade_service.open_trade(
                symbol='R_75',
                signal_direction='BUY',
                entry_price=1.23,
                strategy_name=strategy.name,
            )

            if not trade:
                return False

            closed = trade_service.close_trade(trade, pnl=-10.0, exit_price=1.20, exit_reason='Test loss')
            if closed.status != 'CLOSED':
                return False
            if not abs(risk.get_balance() - 990.0) < 1e-6:
                return False
            if risk.consecutive_losses != 1:
                return False
            return True

        print_section("Testing Trade Closure")
        self.test("Trade closure writes profit and updates risk service", check)

    def validate_bot_engine_risk_config(self):
        """Test 6: Validate bot engine risk configuration propagation"""
        def check():
            bot = DerivBotEngine(strategy_name='trend', balance=2000.0, risk_pct=0.03, max_daily_loss_pct=0.08)
            assert bot.risk_service.risk_pct == 0.03
            assert bot.risk_service.max_daily_loss_pct == 0.08
            assert bot.trade_service.risk_service is bot.risk_service
            return True

        print_section("Testing Bot Engine Risk Wiring")
        self.test("Bot engine creates and wires risk service correctly", check)

    def run_all(self):
        self.validate_imports()
        self.validate_risk_service_basics()
        self.validate_risk_service_stop_conditions()
        self.validate_trade_service_risk_integration()
        self.validate_trade_closure_updates_risk()
        self.validate_bot_engine_risk_config()

        print_section("Phase 5 Summary")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        if self.errors:
            print("Errors:")
            for error in self.errors:
                print(f"  - {error}")

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase5Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
