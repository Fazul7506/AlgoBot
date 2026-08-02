#!/usr/bin/env python
"""
Phase 8 Paper Trading Validation
- Simulated execution
- Real-time testing
- Paper vs live comparison
- Reporting: daily & weekly report generation

Comprehensive validation of paper trading infrastructure.
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

from django.utils import timezone
from trading.services.trade_service import TradeService
from trading.services.risk_service import RiskService
from trading.services.paper_trading_service import PaperTradingService
from trading.services.paper_trading_reporter import PaperTradingReporter
from trading.services.paper_vs_live_comparison import PaperVsLiveComparison
from trading.models.core import Strategy, Trade, PerformanceSnapshot
from trading.services.deriv_client import DerivClient
from trading.services.websocket_manager import WebSocketManager


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase8Validator:
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
            _ = PaperTradingService
            _ = PaperTradingReporter
            _ = PaperVsLiveComparison
            return True

        print_section('Testing imports')
        self.test('Phase 8 imports (paper trading services)', check)

    def validate_open_paper_trade(self):
        def check():
            pts = PaperTradingService(initial_balance=10000.0)
            trade = pts.execute_paper_trade(
                symbol='R_100',
                direction='BUY',
                entry_price=100.0,
                strategy_name='paper_demo',
                confidence=75,
                market_regime='bull',
            )
            return trade is not None and trade.is_paper and trade.status == 'OPEN'

        print_section('Testing open paper trade (demo account)')
        self.test('Open paper trade via PaperTradingService', check)

    def validate_simulated_execution(self):
        def check():
            pts = PaperTradingService(initial_balance=10000.0)
            trade = pts.execute_paper_trade(
                symbol='R_100',
                direction='BUY',
                entry_price=100.0,
                strategy_name='paper_demo',
                confidence=60,
            )
            # Simulate market move and close
            closed = pts.close_paper_trade(trade, exit_price=102.5, exit_reason='simulated')
            return closed.status == 'CLOSED' and closed.is_paper and closed.profit > 0

        print_section('Testing simulated execution (open -> close)')
        self.test('Simulated paper trade execution flow', check)

    def validate_market_simulation(self):
        def check():
            pts = PaperTradingService(initial_balance=10000.0)
            trade = pts.execute_paper_trade(
                symbol='R_100',
                direction='BUY',
                entry_price=100.0,
                strategy_name='paper_demo',
            )
            # Simulate market move
            moves = pts.simulate_market_move('R_100', 100.0, 105.0, open_trades=[trade])
            return len(moves) > 0 and moves[0]['unrealized_pnl'] > 0

        print_section('Testing market simulation (real-time)')
        self.test('Real-time market move simulation', check)

    def validate_account_state(self):
        def check():
            pts = PaperTradingService(initial_balance=10000.0)
            pts.execute_paper_trade('R_100', 'BUY', 100.0, 'paper_demo')
            state = pts.get_account_state()
            return isinstance(state, dict) and 'balance' in state and 'equity' in state

        print_section('Testing account state tracking')
        self.test('Get paper account state', check)

    def validate_performance_snapshot_logging(self):
        def check():
            pts = PaperTradingService(initial_balance=10000.0)
            pts.execute_paper_trade('R_100', 'BUY', 100.0, 'paper_demo')
            snapshot = pts.log_performance_snapshot()
            return snapshot.id is not None and snapshot.is_paper

        print_section('Testing performance snapshots')
        self.test('PerformanceSnapshot creation', check)

    def validate_daily_reporting(self):
        def check():
            # Create a paper trade
            pts = PaperTradingService(initial_balance=10000.0)
            trade = pts.execute_paper_trade('R_100', 'BUY', 100.0, 'paper_demo')
            pts.close_paper_trade(trade, exit_price=102.5)
            
            # Generate daily report
            report = PaperTradingReporter.get_daily_report()
            return (
                isinstance(report, dict) 
                and 'date' in report 
                and report['report_type'] == 'DAILY'
                and 'trades_closed' in report
            )

        print_section('Testing daily reporting')
        self.test('Generate daily paper trading report', check)

    def validate_weekly_reporting(self):
        def check():
            # Create multiple paper trades
            pts = PaperTradingService(initial_balance=10000.0)
            for i in range(3):
                trade = pts.execute_paper_trade(f'R_{100+i*10}', 'BUY', 100.0 + i*5, 'paper_demo')
                pts.close_paper_trade(trade, exit_price=105.0 + i*5)
            
            # Generate weekly report
            report = PaperTradingReporter.get_weekly_report()
            return (
                isinstance(report, dict)
                and 'week_start' in report
                and report['report_type'] == 'WEEKLY'
                and 'daily_summaries' in report
            )

        print_section('Testing weekly reporting')
        self.test('Generate weekly paper trading report', check)

    def validate_csv_export(self):
        def check():
            pts = PaperTradingService(initial_balance=10000.0)
            trade = pts.execute_paper_trade('R_100', 'BUY', 100.0, 'paper_demo')
            pts.close_paper_trade(trade, exit_price=102.5)
            
            daily_csv = PaperTradingReporter.export_daily_report_csv()
            weekly_csv = PaperTradingReporter.export_weekly_report_csv()
            
            return isinstance(daily_csv, str) and isinstance(weekly_csv, str)

        print_section('Testing report export')
        self.test('Export daily and weekly reports as CSV', check)

    def validate_strategy_comparison(self):
        def check():
            # Create paper and live trades
            pts = PaperTradingService(initial_balance=10000.0)
            paper_trade = pts.execute_paper_trade('R_100', 'BUY', 100.0, 'trend_strategy')
            pts.close_paper_trade(paper_trade, exit_price=102.5)
            
            # Live trade
            ts = TradeService()
            live_trade = ts.open_trade(
                symbol='R_100',
                signal_direction='BUY',
                entry_price=100.0,
                strategy_name='trend_strategy',
                is_paper=False,
            )
            ts.close_trade(live_trade, pnl=2.0, exit_price=102.0)
            
            comparison = PaperVsLiveComparison.get_strategy_comparison('trend_strategy')
            return (
                isinstance(comparison, dict)
                and 'paper' in comparison
                and 'live' in comparison
                and 'comparison' in comparison
            )

        print_section('Testing paper vs live comparison')
        self.test('Compare strategy performance paper vs live', check)

    def validate_account_comparison(self):
        def check():
            comparison = PaperVsLiveComparison.get_account_comparison()
            return (
                isinstance(comparison, dict)
                and 'paper' in comparison
                and 'live' in comparison
            )

        print_section('Testing account comparison')
        self.test('Compare overall paper vs live performance', check)

    def validate_risk_adjusted_comparison(self):
        def check():
            pts = PaperTradingService(initial_balance=10000.0)
            for i in range(3):
                trade = pts.execute_paper_trade('R_100', 'BUY', 100.0, 'momentum')
                pts.close_paper_trade(trade, exit_price=101.0 + i)
            
            comparison = PaperVsLiveComparison.get_risk_adjusted_comparison('momentum')
            return (
                isinstance(comparison, dict)
                and 'paper' in comparison
                and 'live' in comparison
            )

        print_section('Testing risk-adjusted comparison')
        self.test('Risk-adjusted returns comparison (Sharpe-like)', check)

    def run_all(self):
        self.validate_imports()
        self.validate_open_paper_trade()
        self.validate_simulated_execution()
        self.validate_market_simulation()
        self.validate_account_state()
        self.validate_performance_snapshot_logging()
        self.validate_daily_reporting()
        self.validate_weekly_reporting()
        self.validate_csv_export()
        self.validate_strategy_comparison()
        self.validate_account_comparison()
        self.validate_risk_adjusted_comparison()

        print_section('Phase 8 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase8Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
