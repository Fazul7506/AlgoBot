"""
Management command to train a LightGBM model on built dataset.
Usage: python manage.py train_lgb --symbol R_50 --timeframe M1
"""
from django.core.management.base import BaseCommand
import os
import numpy as np

from trading.ai.dataset_builder import build_dataset
from trading.models.core import AIModel

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'ai', 'models')
if not os.path.exists(MODEL_DIR):
    os.makedirs(MODEL_DIR, exist_ok=True)


class Command(BaseCommand):
    help = 'Train LightGBM model for a symbol/timeframe'

    def add_arguments(self, parser):
        parser.add_argument('--symbol', required=True)
        parser.add_argument('--timeframe', default='M1')
        parser.add_argument('--window', type=int, default=200)
        parser.add_argument('--horizon', type=int, default=1)

    def handle(self, *args, **options):
        symbol = options['symbol']
        timeframe = options['timeframe']
        window = options['window']
        horizon = options['horizon']

        X, y = build_dataset(symbol, timeframe, window=window, horizon=horizon)
        if X is None or y is None:
            self.stdout.write(self.style.ERROR('Not enough data'))
            return

        try:
            import lightgbm as lgb
            clf = lgb.LGBMClassifier(n_estimators=100, random_state=42)
            clf.fit(X, y)

            import joblib
            model_path = os.path.join(MODEL_DIR, f'{symbol}_{timeframe}_lgb.pkl')
            joblib.dump(clf, model_path)

            ai = AIModel.objects.create(
                name=f'{symbol}_{timeframe}_lgb',
                model_type='lightgbm',
                storage_path=model_path,
                version='1',
                metrics={'n_samples': int(X.shape[0])}
            )
            self.stdout.write(self.style.SUCCESS(f'Saved LightGBM model to {model_path}'))
        except ImportError:
            self.stdout.write(self.style.ERROR('lightgbm not installed. Run: pip install lightgbm joblib'))
