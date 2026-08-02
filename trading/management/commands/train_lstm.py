"""
Management command to train an LSTM model on built dataset.
Usage: python manage.py train_lstm --symbol R_50 --timeframe M1
"""
from django.core.management.base import BaseCommand
import os
import numpy as np

from trading.ai.dataset_builder import build_dataset
from trading.ai.lstm_model import train_lstm
from trading.models.core import AIModel

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'ai', 'models')
if not os.path.exists(MODEL_DIR):
    os.makedirs(MODEL_DIR, exist_ok=True)


class Command(BaseCommand):
    help = 'Train LSTM model for a symbol/timeframe'

    def add_arguments(self, parser):
        parser.add_argument('--symbol', required=True)
        parser.add_argument('--timeframe', default='M1')
        parser.add_argument('--window', type=int, default=200)
        parser.add_argument('--horizon', type=int, default=1)
        parser.add_argument('--seq_length', type=int, default=20)
        parser.add_argument('--epochs', type=int, default=10)

    def handle(self, *args, **options):
        symbol = options['symbol']
        timeframe = options['timeframe']
        window = options['window']
        horizon = options['horizon']
        seq_length = options['seq_length']
        epochs = options['epochs']

        X, y = build_dataset(symbol, timeframe, window=window, horizon=horizon)
        if X is None or y is None:
            self.stdout.write(self.style.ERROR('Not enough data'))
            return

        try:
            model = train_lstm(X, y, seq_length=seq_length, epochs=epochs)
            if model is None:
                self.stdout.write(self.style.ERROR('Failed to train LSTM'))
                return

            model_path = os.path.join(MODEL_DIR, f'{symbol}_{timeframe}_lstm.keras')
            model.save(model_path)

            ai = AIModel.objects.create(
                name=f'{symbol}_{timeframe}_lstm',
                model_type='lstm',
                storage_path=model_path,
                version='1',
                metrics={'n_samples': int(X.shape[0]), 'seq_length': seq_length}
            )
            self.stdout.write(self.style.SUCCESS(f'Saved LSTM model to {model_path}'))
        except ImportError:
            self.stdout.write(self.style.ERROR('tensorflow not installed. Run: pip install tensorflow'))
