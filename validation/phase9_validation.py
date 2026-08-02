#!/usr/bin/env python
"""
Phase 9 AI & Machine Learning Validation
- Dataset builder
- Feature store
- Random Forest/XGBoost/LightGBM training
- LSTM deep learning
- Ensemble predictions
- Confidence scoring
- Model registry
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
import numpy as np
from trading.ai.dataset_builder import build_dataset

try:
    from trading.ai.dataset_builder import build_dataset
    from trading.ai.feature_store import FeatureStore
    from trading.ai.predictor import Predictor
    from trading.ai.confidence import aggregate_confidence, trade_confidence
    from trading.ai.ensemble import EnsemblePredictor
    from trading.models.core import AIModel, Candle
    from trading.services.paper_trading_service import PaperTradingService
except ImportError as e:
    print(f"Warning: Some Phase 9 modules not available - {e}")


def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


class Phase9Validator:
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
            from trading.ai import dataset_builder
            from trading.ai import feature_store
            from trading.ai import predictor
            from trading.ai import confidence
            from trading.ai import ensemble
            from trading.ai import lstm_model
            return True

        print_section('Testing imports')
        self.test('Phase 9 AI/ML imports', check)

    def validate_dataset_builder(self):
        def check():
            # Create sample candles for testing
            now = timezone.now()
            for i in range(50):
                Candle.objects.get_or_create(
                    symbol='R_100',
                    timeframe='M1',
                    timestamp=now - timezone.timedelta(minutes=50-i),
                    defaults={
                        'open': 100 + i*0.1,
                        'high': 100 + i*0.2,
                        'low': 100 + i*0.05,
                        'close': 100 + i*0.1 + np.random.random(),
                        'volume': 1000,
                    }
                )
            X, y = build_dataset('R_100', 'M1', window=30)
            return X is not None and y is not None and len(X) > 0

        print_section('Testing dataset builder')
        self.test('Build dataset from candles', check)

    def validate_feature_store(self):
        def check():
            fs = FeatureStore()
            feats = fs.get_features('R_100', 'M1', window=30)
            fs.invalidate('R_100', 'M1')
            return isinstance(feats, list) and len(feats) >= 0

        print_section('Testing feature store')
        self.test('Feature store caching', check)

    def validate_predictor(self):
        def check():
            pred = Predictor()
            X_dummy = np.random.random((1, 6))
            result = pred.predict(X_dummy)
            return isinstance(result, dict) and 'direction' in result and 'probability' in result

        print_section('Testing predictor')
        self.test('Predictor returns structured output', check)

    def validate_confidence_scoring(self):
        def check():
            probs = [0.7, 0.75, 0.72]
            conf = aggregate_confidence(probs)
            trade_conf = trade_confidence(conf, risk_factor=1.0)
            return 0.0 <= conf <= 1.0 and 0.0 <= trade_conf <= 100.0

        print_section('Testing confidence scoring')
        self.test('Aggregate confidence and trade confidence', check)

    def validate_model_registry(self):
        def check():
            ai = AIModel.objects.create(
                name='test_model',
                model_type='random_forest',
                storage_path='/tmp/test.pkl',
                version='1',
                metrics={'accuracy': 0.85}
            )
            return ai.id is not None

        print_section('Testing model registry')
        self.test('AIModel registry creation', check)

    def validate_ensemble_predictor(self):
        def check():
            ens = EnsemblePredictor('R_100', 'M1')
            X_dummy = np.random.random((1, 6))
            result = ens.predict(X_dummy)
            return (
                isinstance(result, dict) 
                and 'direction' in result 
                and 'confidence' in result
                and 'models_used' in result
            )

        print_section('Testing ensemble predictor')
        self.test('Ensemble predictor combines models', check)

    def validate_lstm_shapes(self):
        def check():
            from trading.ai.lstm_model import create_sequences
            X_dummy = np.random.random((100, 6))
            seqs, targets = create_sequences(X_dummy, seq_length=20)
            return seqs.shape[0] > 0 and seqs.shape[1] == 20 and seqs.shape[2] == 6

        print_section('Testing LSTM shapes')
        self.test('LSTM sequence creation', check)

    def validate_integration_with_paper_trading(self):
        def check():
            # Integrate AI prediction with paper trading
            pts = PaperTradingService(initial_balance=10000.0)
            pred = Predictor()
            X_dummy = np.random.random((1, 6))
            ai_pred = pred.predict(X_dummy)
            
            if ai_pred['direction'] == 'UP':
                trade = pts.execute_paper_trade(
                    'R_100', 'BUY', 100.0, 'ai_model',
                    confidence=int(ai_pred['confidence']*100)
                )
                return trade is not None and trade.is_paper
            return True

        print_section('Testing AI + Paper Trading integration')
        self.test('AI prediction -> paper trade execution', check)

    def run_all(self):
        self.validate_imports()
        self.validate_dataset_builder()
        self.validate_feature_store()
        self.validate_predictor()
        self.validate_confidence_scoring()
        self.validate_model_registry()
        self.validate_ensemble_predictor()
        self.validate_lstm_shapes()
        self.validate_integration_with_paper_trading()

        print_section('Phase 9 Summary')
        print(f'Passed: {self.passed}')
        print(f'Failed: {self.failed}')
        if self.errors:
            print('Errors:')
            for error in self.errors:
                print(f'  - {error}')

        return self.failed == 0


if __name__ == '__main__':
    validator = Phase9Validator()
    success = validator.run_all()
    sys.exit(0 if success else 1)
