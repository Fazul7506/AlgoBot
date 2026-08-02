#!/usr/bin/env python
"""
Phase 3 Technical Analysis Engine - Validation Script
This script validates that all Phase 3 components are properly installed and functional.
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deriv_platform.settings')

try:
    django.setup()
except Exception as e:
    print(f"Error setting up Django: {e}")
    sys.exit(1)

from django.contrib.auth.models import User
from django.utils import timezone
from trading.models.indicators import IndicatorValue, TechnicalSignal, IndicatorProfile, IndicatorAlert
from trading.models.market import MarketSymbol
from trading.services.indicator_service import IndicatorEngine, TrendIndicators, MomentumIndicators, VolatilityIndicators, TrendStrengthIndicators
from trading.services.signal_generator import SignalGenerator
import numpy as np


class Phase3Validator:
    """Validates Phase 3 implementation"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
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
        """Test 1: Validate all imports work"""
        def check():
            from trading.models.indicators import IndicatorValue, TechnicalSignal, IndicatorProfile, IndicatorAlert
            from trading.services.indicator_service import IndicatorEngine
            from trading.services.signal_generator import SignalGenerator
            from trading.serializers.indicators import IndicatorValueSerializer
            from trading.views.indicators import IndicatorValueViewSet
            return True
        
        self.test("Imports", check)
    
    def validate_models_exist(self):
        """Test 2: Validate all models exist"""
        def check():
            assert IndicatorValue._meta.db_table == 'trading_indicatorvalue'
            assert TechnicalSignal._meta.db_table == 'trading_technicalsignal'
            assert IndicatorProfile._meta.db_table == 'trading_indicatorprofile'
            assert IndicatorAlert._meta.db_table == 'trading_indicatoralert'
            return True
        
        self.test("Models exist in database", check)
    
    def validate_model_fields(self):
        """Test 3: Validate model fields"""
        def check():
            # IndicatorValue fields
            assert hasattr(IndicatorValue, 'symbol')
            assert hasattr(IndicatorValue, 'indicator_type')
            assert hasattr(IndicatorValue, 'value')
            
            # TechnicalSignal fields
            assert hasattr(TechnicalSignal, 'signal_type')
            assert hasattr(TechnicalSignal, 'confidence')
            assert hasattr(TechnicalSignal, 'strength')
            
            # IndicatorProfile fields
            assert hasattr(IndicatorProfile, 'profile_type')
            assert hasattr(IndicatorProfile, 'sma_periods')
            
            # IndicatorAlert fields
            assert hasattr(IndicatorAlert, 'alert_type')
            assert hasattr(IndicatorAlert, 'condition_value')
            
            return True
        
        self.test("Model fields defined", check)
    
    def validate_indicator_calculations(self):
        """Test 4: Validate indicator calculations"""
        def check():
            trend_calc = TrendIndicators()
            prices = np.array([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
            
            # Test SMA
            sma = trend_calc.calculate_sma(prices, 5)
            assert isinstance(sma, (int, float, np.number))
            
            # Test EMA
            ema = trend_calc.calculate_ema(prices, 5)
            assert isinstance(ema, (int, float, np.number))
            
            # Test WMA
            wma = trend_calc.calculate_wma(prices, 5)
            assert isinstance(wma, (int, float, np.number))
            
            return True
        
        self.test("Trend indicator calculations", check)
    
    def validate_momentum_indicators(self):
        """Test 5: Validate momentum indicators"""
        def check():
            momentum_calc = MomentumIndicators()
            prices = np.array([44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89])
            
            # Test RSI
            rsi = momentum_calc.calculate_rsi(prices, 14)
            assert 0 <= rsi <= 100
            
            # Test MACD
            macd = momentum_calc.calculate_macd(prices)
            assert isinstance(macd, dict)
            assert 'macd_line' in macd
            
            return True
        
        self.test("Momentum indicator calculations", check)
    
    def validate_volatility_indicators(self):
        """Test 6: Validate volatility indicators"""
        def check():
            volatility_calc = VolatilityIndicators()
            highs = np.array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
            lows = np.array([10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
            closes = np.array([10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5, 19.5])
            
            # Test ATR
            atr = volatility_calc.calculate_atr(highs, lows, closes, 14)
            assert atr > 0
            
            # Test Bollinger Bands
            prices = np.array([20, 21, 22, 21, 20, 21, 22, 23, 22, 21, 20, 21, 22, 23, 24])
            bb = volatility_calc.calculate_bollinger_bands(prices, 5, 2.0)
            assert bb['upper'] > bb['middle']
            assert bb['middle'] > bb['lower']
            
            return True
        
        self.test("Volatility indicator calculations", check)
    
    def validate_trend_strength_indicators(self):
        """Test 7: Validate trend strength indicators"""
        def check():
            trend_strength = TrendStrengthIndicators()
            highs = np.array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20] + [20]*14)
            lows = np.array([10, 11, 12, 13, 14, 15, 16, 17, 18, 19] + [19]*14)
            
            # Test ADX
            adx = trend_strength.calculate_adx(highs, lows, 14)
            assert isinstance(adx, dict)
            assert 'adx' in adx
            
            return True
        
        self.test("Trend strength indicator calculations", check)
    
    def validate_indicator_engine(self):
        """Test 8: Validate IndicatorEngine"""
        def check():
            engine = IndicatorEngine()
            
            # Test trend detection
            indicators = {'SMA20': 20, 'SMA50': 15, 'RSI': 65}
            trend = engine.detect_trend_direction(indicators)
            assert trend in ['STRONG_BULLISH', 'BULLISH', 'NEUTRAL', 'BEARISH', 'STRONG_BEARISH']
            
            # Test signal strength calculation
            strength = engine.calculate_signal_strength(indicators)
            assert 0 <= strength <= 1
            
            return True
        
        self.test("IndicatorEngine functionality", check)
    
    def validate_signal_generator(self):
        """Test 9: Validate SignalGenerator"""
        def check():
            # Create test symbol
            symbol, _ = MarketSymbol.objects.get_or_create(
                symbol='TEST_EUR_USD',
                defaults={'display_name': 'Test Euro USD', 'market_type': 'FOREX'}
            )
            
            generator = SignalGenerator()
            indicators = {
                'SMA20': 1.2345,
                'SMA50': 1.2200,
                'RSI': 65,
            }
            
            signal = generator.generate_signal(
                symbol_obj=symbol,
                timeframe='H1',
                candle_time=timezone.now(),
                indicators=indicators
            )
            
            assert isinstance(signal, dict)
            assert 'signal_type' in signal
            
            return True
        
        self.test("SignalGenerator functionality", check)
    
    def validate_serializers(self):
        """Test 10: Validate serializers"""
        def check():
            from trading.serializers.indicators import (
                IndicatorValueSerializer,
                TechnicalSignalSerializer,
                IndicatorProfileSerializer,
                IndicatorAlertSerializer
            )
            
            assert IndicatorValueSerializer is not None
            assert TechnicalSignalSerializer is not None
            assert IndicatorProfileSerializer is not None
            assert IndicatorAlertSerializer is not None
            
            return True
        
        self.test("Serializers", check)
    
    def validate_viewsets(self):
        """Test 11: Validate ViewSets"""
        def check():
            from trading.views.indicators import (
                IndicatorValueViewSet,
                TechnicalSignalViewSet,
                IndicatorProfileViewSet,
                IndicatorAlertViewSet,
                IndicatorDashboardViewSet
            )
            
            assert hasattr(IndicatorValueViewSet, 'list')
            assert hasattr(IndicatorValueViewSet, 'retrieve')
            assert hasattr(TechnicalSignalViewSet, 'list')
            assert hasattr(IndicatorProfileViewSet, 'perform_create')
            
            return True
        
        self.test("ViewSets", check)
    
    def validate_admin(self):
        """Test 12: Validate admin classes"""
        def check():
            from django.contrib import admin
            
            # Check if models are registered in admin
            assert IndicatorValue in admin.site._registry
            assert TechnicalSignal in admin.site._registry
            assert IndicatorProfile in admin.site._registry
            assert IndicatorAlert in admin.site._registry
            
            return True
        
        self.test("Admin registration", check)
    
    def validate_database_tables(self):
        """Test 13: Validate database tables"""
        def check():
            from django.db import connection
            
            tables = connection.introspection.table_names()
            
            assert 'trading_indicatorvalue' in tables
            assert 'trading_technicalsignal' in tables
            assert 'trading_indicatorprofile' in tables
            assert 'trading_indicatoralert' in tables
            
            return True
        
        self.test("Database tables", check)
    
    def validate_model_creation(self):
        """Test 14: Validate model creation"""
        def check():
            # Create test data
            symbol, _ = MarketSymbol.objects.get_or_create(
                symbol='VAL_EUR_USD',
                defaults={'display_name': 'Validation Euro USD', 'market_type': 'FOREX'}
            )
            
            # Test IndicatorValue
            ind_val = IndicatorValue.objects.create(
                symbol=symbol,
                indicator_type='SMA',
                timeframe='H1',
                period=20,
                value=1.2345,
                candle_time=timezone.now()
            )
            assert ind_val.id is not None
            
            # Test TechnicalSignal
            signal = TechnicalSignal.objects.create(
                symbol=symbol,
                timeframe='H1',
                signal_type='BULLISH',
                signal_source='SMA_Cross',
                confidence=0.85,
                strength=0.90,
                candle_time=timezone.now()
            )
            assert signal.id is not None
            
            # Test IndicatorProfile
            user, _ = User.objects.get_or_create(username='validator')
            profile, _ = IndicatorProfile.objects.get_or_create(
                user=user,
                defaults={'profile_type': 'BALANCED'}
            )
            assert profile.id is not None
            
            # Test IndicatorAlert
            alert = IndicatorAlert.objects.create(
                user=user,
                symbol=symbol,
                alert_type='THRESHOLD',
                indicator_type='RSI',
                condition_value=70.0,
                comparison='>'
            )
            assert alert.id is not None
            
            return True
        
        self.test("Model creation", check)
    
    def validate_model_queries(self):
        """Test 15: Validate model queries"""
        def check():
            # Test IndicatorValue query
            ind_values = IndicatorValue.objects.filter(indicator_type='SMA')
            assert ind_values is not None
            
            # Test TechnicalSignal query
            signals = TechnicalSignal.objects.filter(signal_type='BULLISH')
            assert signals is not None
            
            # Test IndicatorProfile query
            profiles = IndicatorProfile.objects.all()
            assert profiles is not None
            
            # Test IndicatorAlert query
            alerts = IndicatorAlert.objects.filter(is_active=True)
            assert alerts is not None
            
            return True
        
        self.test("Model queries", check)
    
    def run_all_tests(self):
        """Run all validation tests"""
        print("\n" + "="*60)
        print("Phase 3 - Technical Analysis Engine Validation")
        print("="*60 + "\n")
        
        self.validate_imports()
        self.validate_models_exist()
        self.validate_model_fields()
        self.validate_indicator_calculations()
        self.validate_momentum_indicators()
        self.validate_volatility_indicators()
        self.validate_trend_strength_indicators()
        self.validate_indicator_engine()
        self.validate_signal_generator()
        self.validate_serializers()
        self.validate_viewsets()
        self.validate_admin()
        self.validate_database_tables()
        self.validate_model_creation()
        self.validate_model_queries()
        
        print("\n" + "="*60)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        print("="*60 + "\n")
        
        if self.failed > 0:
            print("Failed tests:")
            for error in self.errors:
                print(f"  - {error}")
            return False
        else:
            print("All validation tests passed!")
            return True


if __name__ == '__main__':
    validator = Phase3Validator()
    success = validator.run_all_tests()
    sys.exit(0 if success else 1)
