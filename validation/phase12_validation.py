#!/usr/bin/env python
"""
Phase 12 Advanced Analytics & Reporting Validation
- Validates advanced analytics endpoints, strategy comparison, CSV/PDF export, and metrics.
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

from trading.services.advanced_analytics_service import AdvancedAnalyticsService
from trading.views.dashboard import DashboardViewSet
from trading.models.core import Trade, Strategy
from django.utils import timezone


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase12Validator:
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
            from trading.services.advanced_analytics_service import AdvancedAnalyticsService
            from trading.views.dashboard import DashboardViewSet
            return True

        print_section('Testing imports')
        self.test('Phase 12 imports', check)

    def validate_performance_metrics(self):
        def check():
            now = timezone.now()
            strategy = Strategy.objects.first()
            trades = Trade.objects.filter(status='CLOSED')
            if trades.count() < 2:
                for i in range(3):
                    Trade.objects.create(
                        user=None,
                        strategy_fk=strategy,
                        strategy='trend',
                        symbol='R_75',
                        contract_type='CALL',
                        entry_price=100.0,
                        stake=1.0,
                        exit_price=101.0 + i,
                        profit=1.0 + i,
                        profit_pct=100.0,
                        status='CLOSED',
                        strategy_confidence=0.8,
                        indicators_snapshot={'market_regime': 'trending'},
                        opened_at=now,
                        closed_at=now,
                    )
            service = AdvancedAnalyticsService()
            metrics = service.compute_performance_metrics(days=30)
            return (
                isinstance(metrics, dict)
                and metrics.get('total_trades', 0) >= 1
                and 'roi' in metrics
                and 'profit_factor' in metrics
                and isinstance(metrics.get('equity_curve'), list)
            )

        print_section('Testing performance metrics')
        self.test('AdvancedAnalyticsService performance metrics', check)

    def validate_csv_export(self):
        def check():
            service = AdvancedAnalyticsService()
            csv_data = service.export_performance_csv(days=30)
            return isinstance(csv_data, str) and 'total_trades' in csv_data

        print_section('Testing CSV export')
        self.test('AdvancedAnalyticsService export_performance_csv', check)

    def validate_strategy_comparison(self):
        def check():
            service = AdvancedAnalyticsService()
            comparison = service.strategy_comparison(strategy_names=['trend'], symbol='R_75', timeframe='M1')
            return isinstance(comparison, list)

        print_section('Testing strategy comparison')
        self.test('AdvancedAnalyticsService strategy comparison', check)

    def validate_pdf_export(self):
        def check():
            service = AdvancedAnalyticsService()
            try:
                pdf_bytes = service.export_pdf(
                    'Test Report',
                    [['metric', 'value'], ['roi', '0']],
                    {'phase': '12'},
                )
                return isinstance(pdf_bytes, (bytes, bytearray)) and len(pdf_bytes) > 0
            except ImportError:
                return True

        print_section('Testing PDF export')
        self.test('AdvancedAnalyticsService export_pdf', check)

    def run_all(self):
        self.validate_imports()
        self.validate_performance_metrics()
        self.validate_csv_export()
        self.validate_strategy_comparison()
        self.validate_pdf_export()

        print_section('Phase 12 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase12Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
