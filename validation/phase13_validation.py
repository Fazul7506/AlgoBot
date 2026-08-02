#!/usr/bin/env python
"""Phase 13 Notifications Validation"""

import os
import sys
from pathlib import Path
import django

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deriv_platform.settings')
django.setup()

from trading.services.notification_service import NotificationService
from trading.services.trade_service import TradeService
from trading.models.core import Trade


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase13Validator:
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

    def validate_service(self):
        def check():
            service = NotificationService()
            result = service.send('trade_opened', {'symbol': 'R_75', 'strategy': 'trend'}, channels=['push'])
            return result['alert_type'] == 'trade_opened' and 'push' in result['sent']

        print_section('Testing notification service')
        self.test('NotificationService sends alerts', check)

    def validate_trade_lifecycle(self):
        def check():
            trade = Trade.objects.create(
                strategy='trend',
                symbol='R_75',
                contract_type='CALL',
                entry_price=100.0,
                stake=1.0,
                profit=0.0,
                profit_pct=0.0,
                status='OPEN',
                strategy_confidence=0.8,
            )
            TradeService().close_trade(trade, pnl=0.5, exit_price=101.0, exit_reason='target')
            return trade.status == 'CLOSED'

        print_section('Testing trade lifecycle notifications')
        self.test('TradeService close_trade completes', check)

    def run_all(self):
        self.validate_service()
        self.validate_trade_lifecycle()
        print_section('Phase 13 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')
        return self.failed == 0


if __name__ == '__main__':
    validator = Phase13Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
