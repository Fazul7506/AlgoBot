#!/usr/bin/env python
"""
Phase 6 Professional Trader Logic - Validation Script
Validates market structure detection, order blocks, fair value gaps, support/resistance,
liquidity zones, signal confirmation, and dashboard structure integration.
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

from django.utils import timezone
from django.contrib.auth.models import User
from trading.models.market import MarketSymbol
from trading.services.market_structure import MarketStructureDetector
from trading.services.indicator_service import IndicatorEngine
from trading.services.signal_generator import SignalGenerator


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase6Validator:
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
            from trading.services.market_structure import MarketStructureDetector
            from trading.services.indicator_service import IndicatorEngine
            from trading.services.signal_generator import SignalGenerator
            return True

        print_section('Testing imports')
        self.test('Phase 6 imports', check)

    def validate_market_structure_detector(self):
        def check():
            detector = MarketStructureDetector(lookback=2)
            highs = [10, 11, 12, 13, 14, 15]
            lows = [9, 10, 11, 12, 13, 14]
            swings = detector.detect_swings(highs, lows)
            structure = detector.determine_structure(swings)
            bos = detector.detect_break_of_structure([10, 11, 12, 13, 14, 15.5], swings)
            coc = detector.detect_change_of_character([10, 11, 12, 13, 16, 15.01], swings)
            ob = detector.detect_order_blocks([10, 11, 10, 9, 12], [11, 12, 11, 10, 13], [9, 10, 9, 8, 11], [10.5, 11.5, 10.2, 9.8, 12.5], multiplier=0.5)
            fvg = detector.detect_fair_value_gaps([10, 12, 11, 13], [11, 13, 12, 14], [9, 11, 10, 12], [12, 11, 13, 12])
            zones = detector.detect_support_resistance_zones(highs, lows)
            pools = detector.detect_liquidity_pools(highs, lows)
            equal_levels = detector.detect_equal_price_levels(highs, lows)
            return structure in ['UPTREND', 'DOWNTREND', 'RANGE', 'UNKNOWN'] and bos is not None and isinstance(ob, list) and isinstance(fvg, list) and isinstance(zones, list) and isinstance(pools, list)

        print_section('Testing market structure detector')
        self.test('Market structure detector outputs', check)

    def validate_indicator_engine_structure(self):
        def check():
            engine = IndicatorEngine()
            opens = [10, 11, 12, 11, 13, 12]
            highs = [11, 12, 13, 12, 14, 13]
            lows = [9, 10, 11, 10, 12, 11]
            closes = [11, 12, 12.5, 11.5, 13.5, 12.8]
            multi_timeframes = {
                'M1': {'structure': 'UPTREND'},
                'M5': {'structure': 'UPTREND'},
                'M15': {'structure': 'UPTREND'},
                'H1': {'structure': 'UPTREND'},
            }
            insight = engine.calculate_market_structure(opens, highs, lows, closes, multi_timeframes=multi_timeframes)
            return (
                isinstance(insight, dict)
                and 'structure' in insight
                and 'break_of_structure' in insight
                and 'equal_highs' in insight
                and 'equal_lows' in insight
                and 'alignment' in insight
            )

        print_section('Testing indicator engine structure')
        self.test('Indicator engine market structure', check)

    def validate_signal_confirmation(self):
        def check():
            symbol, _ = MarketSymbol.objects.get_or_create(symbol='PHASE6_TEST', defaults={'display_name': 'Phase 6 Test', 'market_type': 'FOREX'})
            generator = SignalGenerator()
            indicators = {
                'break_of_structure': {'type': 'BOS_UP', 'level': 12.0, 'price': 12.5},
                'rsi': 45,
                'adx': 30,
                'adx_plus_di': 26,
                'adx_minus_di': 18,
                'sma_20': 12.5,
                'sma_50': 12.0,
                'ema_12': 12.4,
                'ema_26': 12.1,
                'equal_lows': [{'price': 12.0, 'count': 2}],
            }
            signal = generator.generate_signal(symbol, 'H1', timezone.now(), indicators)
            return signal is not None and signal['signal_type'] in ['BULLISH', 'BEARISH', 'STRONG_BULLISH', 'STRONG_BEARISH']

        print_section('Testing signal confirmation')
        self.test('Signal generator confirms structure signals', check)

    def validate_multi_timeframe_alignment(self):
        def check():
            detector = MarketStructureDetector(lookback=2)
            structures = {
                'M1': {'structure': 'UPTREND'},
                'M5': {'structure': 'UPTREND'},
                'M15': {'structure': 'UPTREND'},
                'H1': {'structure': 'UPTREND'},
            }
            return detector.multi_timeframe_alignment(structures) == 'BULLISH_ALIGNMENT'

        print_section('Testing multi-timeframe alignment')
        self.test('Multi-timeframe alignment recognized', check)

    def run_all(self):
        self.validate_imports()
        self.validate_market_structure_detector()
        self.validate_indicator_engine_structure()
        self.validate_signal_confirmation()
        self.validate_multi_timeframe_alignment()

        print_section('Phase 6 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase6Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
