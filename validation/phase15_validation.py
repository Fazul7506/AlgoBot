#!/usr/bin/env python
"""
Phase 15 Copy Trading Validation Script

Validates copy-trading models, services, and API handlers.
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

from django.conf import settings


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase15Validator:
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

    def validate_models(self):
        from trading import models as trading_models

        def check():
            required = ['CopyFollow', 'LeaderStats', 'CopyTrade']
            missing = [name for name in required if not hasattr(trading_models, name)]
            if missing:
                for name in missing:
                    print(f'  - missing model: {name}')
                return False
            return True

        print_section('Models')
        self.test('Copy trading models exist', check)

    def validate_service(self):
        def check():
            from trading.services.copy_service import CopyService
            svc = CopyService()
            return hasattr(svc, 'follow') and hasattr(svc, 'unfollow') and hasattr(svc, 'handle_leader_trade')

        print_section('Service')
        self.test('CopyService exposes follow/unfollow/handle_leader_trade', check)

    def validate_api(self):
        def check():
            from django.urls import get_resolver
            from trading.views.copy_trading import CopyTradingViewSet
            resolver = get_resolver(None)
            routes = [getattr(p.pattern, '_route', str(p.pattern)) for p in resolver.url_patterns]
            return any('copy-trading' in route for route in routes)

        print_section('API')
        self.test('Copy trading API registered', check)

    def validate_leader_integration(self):
        def check():
            from trading.services.trade_service import TradeService
            import inspect
            src = inspect.getsource(TradeService.open_trade)
            return 'CopyService().handle_leader_trade' in src

        print_section('Leader integration')
        self.test('TradeService invokes CopyService for leader trades', check)

    def run_all(self):
        self.validate_models()
        self.validate_service()
        self.validate_api()
        self.validate_leader_integration()

        print_section('Phase 15 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase15Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
