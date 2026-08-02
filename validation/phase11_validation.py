#!/usr/bin/env python
"""
Phase 11 Self-Learning System Validation
- Validates trade analysis, model comparison, and retraining orchestration.
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

from trading.services.self_learning_service import SelfLearningService
from trading.models.core import AIModel, Trade, Strategy
from trading.ai.model_manager import ModelManager
from trading.ai.trade_analysis import TradePatternRecognizer
from trading.ai.learning_engine import SelfLearningEngine
from trading.models.core import Candle
from django.utils import timezone


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase11Validator:
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
            from trading.services.self_learning_service import SelfLearningService
            from trading.ai.learning_engine import SelfLearningEngine
            from trading.ai.trade_analysis import TradePatternRecognizer
            from trading.ai.model_manager import ModelManager
            return True

        print_section('Testing imports')
        self.test('Phase 11 imports', check)

    def validate_trade_analysis(self):
        def check():
            now = timezone.now()
            for i in range(5):
                Trade.objects.create(
                    symbol='R_100',
                    contract_type='CALL',
                    entry_price=100.0,
                    stake=1.0,
                    exit_price=101.0,
                    profit=1.0,
                    profit_pct=100.0,
                    status='CLOSED',
                    strategy='trend',
                    strategy_confidence=0.8,
                    indicators_snapshot={'market_regime': 'trending'},
                    opened_at=now,
                    closed_at=now,
                )
            analysis = TradePatternRecognizer.analyze_closed_trades(symbol='R_100', strategy_name='trend', days=1)
            return analysis['total_trades'] >= 5 and 'regime_breakdown' in analysis

        print_section('Testing trade pattern analysis')
        self.test('TradePatternRecognizer analysis', check)

    def validate_model_manager(self):
        def check():
            ModelManager.list_models('R_100', 'M1')
            return True

        print_section('Testing model manager')
        self.test('ModelManager list models', check)

    def validate_retrain_command(self):
        def check():
            service = SelfLearningService()
            result = service.review_and_retrain(symbol='R_100', timeframe='M1', strategy_name='trend', days=1, force=True)
            return 'analysis' in result and 'retrain_results' in result

        print_section('Testing retrain orchestration')
        self.test('SelfLearningService review and retrain', check)

    def run_all(self):
        self.validate_imports()
        self.validate_trade_analysis()
        self.validate_model_manager()
        self.validate_retrain_command()

        print_section('Phase 11 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase11Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
