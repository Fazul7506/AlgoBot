#!/usr/bin/env python
"""
Phase 10 Market Regime Detection - Validation Script
Validates market regime detection, strategy switching, and regime dashboard support.
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

from trading.services.market_regime import MarketRegimeDetector
from trading.strategies.strategy_manager import StrategyManager
from trading.models.core import Candle


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase10Validator:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def test(self, name, func):
        try:
            if func():
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
            from trading.services.market_regime import MarketRegimeDetector
            from trading.strategies.strategy_manager import StrategyManager
            return True

        print_section('Testing imports')
        self.test('Phase 10 imports', check)

    def validate_regime_detection(self):
        def check():
            quiet = MarketRegimeDetector.detect([100] * 40)
            trending = MarketRegimeDetector.detect([100 + i * 0.5 for i in range(40)])
            volatile = MarketRegimeDetector.detect([100 + ((-1) ** i) * i * 0.5 for i in range(40)])
            ranging = MarketRegimeDetector.detect([100 + ((-1) ** i) * 0.5 for i in range(40)])
            return (
                quiet == 'quiet' and
                trending == 'trending' and
                volatile == 'volatile' and
                ranging == 'ranging'
            )

        print_section('Testing market regime detection')
        self.test('Regime detection classification', check)

    def validate_strategy_switching(self):
        def check():
            manager = StrategyManager(default='trend', auto_regime=True)
            strategy_before = manager.strategy_name
            manager.process_tick('R_75', [100] * 40)
            quiet_strategy = manager.strategy_name
            manager.set_strategy('trend')
            manager.process_tick('R_75', [100 + i * 0.6 for i in range(40)])
            trending_strategy = manager.strategy_name
            return quiet_strategy != strategy_before and trending_strategy == 'trend'

        print_section('Testing strategy manager regime switching')
        self.test('Strategy manager switches based on regime', check)

    def run_all(self):
        self.validate_imports()
        self.validate_regime_detection()
        self.validate_strategy_switching()

        print_section('Phase 10 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase10Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
