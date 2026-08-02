#!/usr/bin/env python
"""
Phase 7 Backtesting System - Validation Script
Tests historical replay, performance metrics, reports, and optimization interfaces.
"""

import os
import sys
from pathlib import Path
import django

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deriv_platform.settings')
django.setup()

import numpy as np
from django.utils import timezone
from trading.models.core import Strategy, Tick, Candle
from trading.strategies import registry
from trading.analytics.backtester import StrategyBacktester, StrategyOptimizer
from trading.strategies.strategy_service import StrategyService


def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase7Validator:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def test(self, name, func):
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
            print(f"[FAIL] {name}: {e}")
            self.failed += 1
            self.errors.append(f"{name}: {e}")

    def validate_imports(self):
        def check():
            from trading.analytics.backtester import StrategyBacktester, StrategyOptimizer
            from trading.strategies.strategy_service import StrategyService
            return True

        print_section('Testing imports')
        self.test('Phase 7 imports', check)

    def validate_candle_replay_backtester(self):
        def check():
            candles = [
                {'open': 100, 'high': 105, 'low': 99, 'close': 104, 'timestamp': timezone.now()},
                {'open': 104, 'high': 106, 'low': 103, 'close': 105, 'timestamp': timezone.now()},
                {'open': 105, 'high': 107, 'low': 104, 'close': 106, 'timestamp': timezone.now()},
                {'open': 106, 'high': 108, 'low': 105, 'close': 107, 'timestamp': timezone.now()},
                {'open': 107, 'high': 109, 'low': 106, 'close': 108, 'timestamp': timezone.now()},
                {'open': 108, 'high': 110, 'low': 107, 'close': 109, 'timestamp': timezone.now()},
            ]
            strategy_cls = registry.get('trend')
            strategy = strategy_cls(short_window=2, mid_window=3, long_window=4)
            backtester = StrategyBacktester(strategy, candles, min_history=4)
            result = backtester.run()
            return isinstance(result, dict) and 'equity_curve' in result and 'monthly_returns' in result and 'trade_distribution' in result

        print_section('Testing candle replay backtester')
        self.test('Candle replay produces metrics and reports', check)

    def validate_tick_replay_backtester(self):
        def check():
            ticks = [100, 101, 102, 101, 103, 104, 105, 104, 106, 107]
            strategy_cls = registry.get('trend')
            strategy = strategy_cls(short_window=2, mid_window=3, long_window=4)
            backtester = StrategyBacktester(strategy, ticks, min_history=4)
            result = backtester.run()
            return isinstance(result, dict) and 'win_rate' in result and 'profit_factor' in result and 'sharpe_ratio' in result

        print_section('Testing tick replay backtester')
        self.test('Tick replay produces performance metrics', check)

    def validate_reports(self):
        def check():
            ticks = [100, 101, 102, 101, 103, 104, 105, 104, 106, 107]
            strategy_cls = registry.get('trend')
            strategy = strategy_cls(short_window=2, mid_window=3, long_window=4)
            backtester = StrategyBacktester(strategy, ticks, min_history=4)
            result = backtester.run()
            equity_curve = backtester.equity_curve()
            monthly_returns = backtester.monthly_returns()
            distribution = backtester.trade_distribution()

            return (
                isinstance(equity_curve, list)
                and isinstance(monthly_returns, dict)
                and isinstance(distribution, dict)
                and len(equity_curve) >= 0
                and 'BUY' in distribution and 'SELL' in distribution
            )

        print_section('Testing reports')
        self.test('Reports generate equity curve, monthly returns, and trade distribution', check)

    def validate_optimizer(self):
        def check():
            ticks = [100, 101, 102, 101, 103, 104, 105, 104, 106, 107, 108, 109, 110, 109, 111, 112, 113]
            strategy_cls = registry.get('trend')
            optimizer = StrategyOptimizer(strategy_cls, ticks, param_grid={
                'short_window': [2, 3],
                'mid_window': [3, 4],
                'long_window': [4, 5],
            })
            best = optimizer.grid_search(top_n=1)
            return isinstance(best, list) and len(best) == 1 and 'params' in best[0] and 'metrics' in best[0]

        print_section('Testing optimizer')
        self.test('Optimizer grid search returns candidate parameters', check)

    def validate_walk_forward_optimization(self):
        def check():
            ticks = [100, 101, 102, 103, 102, 104, 103, 105, 107, 106, 108, 110, 109, 111, 112, 113, 114, 115, 116, 117]
            strategy_cls = registry.get('trend')
            optimizer = StrategyOptimizer(strategy_cls, ticks, param_grid={
                'short_window': [2, 3],
                'mid_window': [3, 4],
                'long_window': [4, 5],
            }, min_history=4)
            result = optimizer.walk_forward_test(train_size=10, test_size=5, step_size=2)
            return isinstance(result, dict) and 'folds' in result and isinstance(result['folds'], list)

        print_section('Testing walk-forward optimization')
        self.test('Walk-forward optimization returns fold summaries', check)

    def run_all(self):
        self.validate_imports()
        self.validate_candle_replay_backtester()
        self.validate_tick_replay_backtester()
        self.validate_reports()
        self.validate_optimizer()
        self.validate_walk_forward_optimization()

        print_section('Phase 7 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase7Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
